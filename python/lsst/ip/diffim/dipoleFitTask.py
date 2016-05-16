from __future__ import absolute_import, division, print_function
#
# LSST Data Management System
# Copyright 2008-2016 AURA/LSST.
#
# This product includes software developed by the
# LSST Project (http://www.lsst.org/).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the LSST License Statement and
# the GNU General Public License along with this program.  If not,
# see <https://www.lsstcorp.org/LegalNotices/>.
#

import numpy as np

# LSST imports
import lsst.afw.geom as afwGeom
import lsst.afw.image as afwImage
import lsst.meas.base as measBase
import lsst.afw.table as afwTable
import lsst.afw.detection as afwDet
import lsst.pex.exceptions as pexExcept
import lsst.pex.logging as pexLog
import lsst.pex.config as pexConfig
from lsst.pipe.base import Struct

__all__ = ("DipoleFitTask", "DipoleFitPlugin", "DipoleFitTaskConfig", "DipoleFitPluginConfig")


# Create a new measurement task (`DipoleFitTask`) that can handle all other SFM tasks but can
# pass a separate pos- and neg- exposure/image to the `DipoleFitPlugin`s `run()` method.


class DipoleFitPluginConfig(measBase.SingleFramePluginConfig):
    """!Configuration for DipoleFitPlugin
    """

    maxSeparation = pexConfig.Field(
        dtype=float, default=5.,
        doc="Assume dipole is not separated by more than maxSeparation * psfSigma")

    relWeight = pexConfig.Field(
        dtype=float, default=0.5,
        doc="""Relative weighting of pre-subtraction images (higher -> greater influence of pre-sub.
        images on fit)""")

    tolerance = pexConfig.Field(
        dtype=float, default=1e-7,
        doc="Fit tolerance")

    fitBackground = pexConfig.Field(
        dtype=int, default=1,
        doc="""Set whether and how to fit for linear gradient in pre-sub. images. Possible values:
        0: do not fit background at all
        1 (default): pre-fit the background using linear least squares and then do not fit it as part
            of the dipole fitting optimization
        2: pre-fit the background using linear least squares (as in 1), and use the parameter
            estimates from that fit as starting parameters for an integrated "re-fit" of the background
        """)

    fitSeparateNegParams = pexConfig.Field(
        dtype=bool, default=False,
        doc="Include parameters to fit for negative values (flux, gradient) separately from pos.")

    # Config params for classification of detected diaSources as dipole or not
    minSn = pexConfig.Field(
        dtype=float, default=np.sqrt(2) * 5.0,
        doc="Minimum quadrature sum of positive+negative lobe S/N to be considered a dipole")

    maxFluxRatio = pexConfig.Field(
        dtype=float, default=0.65,
        doc="Maximum flux ratio in either lobe to be considered a dipole")

    maxChi2DoF = pexConfig.Field(
        dtype=float, default=0.05,
        doc="""Maximum Chi2/DoF significance of fit to be considered a dipole.
        Default value means \"Choose a chi2DoF corresponding to a significance level of at most 0.05\"
        (note this is actually a significance, not a chi2 value).""")


class DipoleFitTaskConfig(measBase.SingleFrameMeasurementConfig):
    """!Measurement of detected diaSources as dipoles"""

    def setDefaults(self):
        measBase.SingleFrameMeasurementConfig.setDefaults(self)

        self.plugins.names = ["base_CircularApertureFlux",
                              "base_PixelFlags",
                              "base_SkyCoord",
                              "base_PsfFlux",
                              "ip_diffim_NaiveDipoleCentroid",
                              "ip_diffim_NaiveDipoleFlux",
                              "ip_diffim_PsfDipoleFlux"
                              ]

        self.slots.calibFlux = None
        self.slots.modelFlux = None
        self.slots.instFlux = None
        self.slots.shape = None
        self.slots.centroid = "ip_diffim_NaiveDipoleCentroid"
        self.doReplaceWithNoise = False


class DipoleFitTask(measBase.SingleFrameMeasurementTask):
    """!Subclass of SingleFrameMeasurementTask which accepts up to three input images in its run() method.

    Because it subclasses SingleFrameMeasurementTask, and calls
    SingleFrameMeasurementTask.run() from its run() method, it still
    can be used identically to a standard SingleFrameMeasurementTask.
    """

    ConfigClass = DipoleFitTaskConfig
    _DefaultName = "ip_diffim_DipoleFit"

    def __init__(self, schema, algMetadata=None, **kwds):

        measBase.SingleFrameMeasurementTask.__init__(self, schema, algMetadata, **kwds)

        dpFitPluginConfig = self.config.plugins['ip_diffim_DipoleFit']

        self.dipoleFitter = DipoleFitPlugin(dpFitPluginConfig, name=self._DefaultName,
                                            schema=schema, metadata=algMetadata)

    def run(self, sources, exposure, posExp=None, negExp=None, **kwds):
        """!Run dipole measurement and classification

        @param sources   diaSources that will be measured using dipole measurement
        @param exposure  Difference exposure on which the diaSources were detected; exposure = posExp - negExp
        @param posExp    "Positive" exposure, typically a science exposure, or None if unavailable
        @param negExp    "Negative" exposure, typically a template exposure, or None if unavailable
        @param **kwds    Sent to SingleFrameMeasurementTask

        @note When `posExp` is `None`, will compute `posImage = exposure + negExp`.
        Likewise, when `negExp` is `None`, will compute `negImage = posExp - exposure`.
        If both `posExp` and `negExp` are `None`, will attempt to fit the dipole to just the `exposure`
        with no constraint.
        """

        measBase.SingleFrameMeasurementTask.run(self, sources, exposure, **kwds)

        if not sources:
            return

        for source in sources:
            self.dipoleFitter.measure(source, exposure, posExp, negExp)


class DipoleModel(object):
    """!Lightweight class containing methods for generating a dipole model for fitting
    to sources in diffims, used by DipoleFitAlgorithm.

    This code is documented in DMTN-007 (http://dmtn-007.lsst.io).
    """

    def __init__(self):
        import lsstDebug
        self.debug = lsstDebug.Info(__name__).debug

    def makeBackgroundModel(self, in_x, pars=None):
        """!Generate gradient model (2-d array) with up to 2nd-order polynomial

        @param in_x (2, w, h)-dimensional `numpy.array`, containing the
        input x,y meshgrid providing the coordinates upon which to
        compute the gradient. This will typically be generated via
        `_generateXYGrid()`. `w` and `h` correspond to the width and
        height of the desired grid.
        @param pars Up to 6 floats for up
        to 6 2nd-order 2-d polynomial gradient parameters, in the
        following order: (intercept, x, y, xy, x**2, y**2). If `pars`
        is emtpy or `None`, do nothing and return `None` (for speed).

        @return None, or 2-d numpy.array of width/height matching
        input bbox, containing computed gradient values.
        """

        # Don't fit for other gradient parameters if the intercept is not included.
        if (pars is None) or (len(pars) <= 0) or (pars[0] is None):
            return

        y, x = in_x[0, :], in_x[1, :]
        gradient = np.full_like(x, pars[0], dtype='float64')
        if len(pars) > 1 and pars[1] is not None:
            gradient += pars[1] * x
        if len(pars) > 2 and pars[2] is not None:
            gradient += pars[2] * y
        if len(pars) > 3 and pars[3] is not None:
            gradient += pars[3] * (x * y)
        if len(pars) > 4 and pars[4] is not None:
            gradient += pars[4] * (x * x)
        if len(pars) > 5 and pars[5] is not None:
            gradient += pars[5] * (y * y)

        return gradient

    def _generateXYGrid(self, bbox):
        """!Generate a meshgrid covering the x,y coordinates bounded by bbox

        @param bbox input BoundingBox defining the coordinate limits
        @return in_x (2, w, h)-dimensional numpy array containing the grid indexing over x- and
        y- coordinates

        @see makeBackgroundModel
        """

        x, y = np.mgrid[bbox.getBeginY():bbox.getEndY(), bbox.getBeginX():bbox.getEndX()]
        in_x = np.array([y, x]).astype(np.float64)
        in_x[0, :] -= np.mean(in_x[0, :])
        in_x[1, :] -= np.mean(in_x[1, :])
        return in_x

    def _getHeavyFootprintSubimage(self, fp, badfill=np.nan, grow=0):
        """!Extract the image from a `HeavyFootprint` as an `afwImage.ImageF`.

        @param fp HeavyFootprint to use to generate the subimage
        @param badfill Value to fill in pixels in extracted image that are outside the footprint
        @param grow Optionally grow the footprint by this amount before extraction

        @return an `afwImage.ImageF` containing the subimage
        """
        hfp = afwDet.HeavyFootprintF_cast(fp)
        bbox = hfp.getBBox()
        if grow > 0:
            bbox.grow(grow)

        subim2 = afwImage.ImageF(bbox, badfill)
        afwDet.expandArray(hfp, hfp.getImageArray(), subim2.getArray(), bbox.getCorners()[0])
        return subim2

    def fitFootprintBackground(self, source, posImage, order=1):
        """!Fit a linear (polynomial) model of given order (max 2) to the background of a footprint.

        Only fit the pixels OUTSIDE of the footprint, but within its bounding box.

        @param source SourceRecord, the footprint of which is to be fit
        @param posImage The exposure from which to extract the footprint subimage
        @param order Polynomial order of background gradient to fit.

        @return pars `tuple` of length (1 if order==0; 3 if order==1; 6 if order == 2),
        containing the resulting fit parameters

        @todo look into whether to use afwMath background methods -- see
        http://lsst-web.ncsa.illinois.edu/doxygen/x_masterDoxyDoc/_background_example.html
        """

        fp = source.getFootprint()
        bbox = fp.getBBox()
        bbox.grow(3)
        posImg = afwImage.ImageF(posImage.getMaskedImage().getImage(), bbox, afwImage.PARENT)

        # This code constructs the footprint image so that we can identify the pixels that are
        # outside the footprint (but within the bounding box). These are the pixels used for
        # fitting the background.
        posHfp = afwDet.HeavyFootprintF(fp, posImage.getMaskedImage())
        posFpImg = self._getHeavyFootprintSubimage(posHfp, grow=3)

        isBg = np.isnan(posFpImg.getArray()).ravel()

        data = posImg.getArray().ravel()
        data = data[isBg]
        B = data

        x, y = np.mgrid[bbox.getBeginY():bbox.getEndY(), bbox.getBeginX():bbox.getEndX()]
        x = x.astype(np.float64).ravel()
        x -= np.mean(x)
        x = x[isBg]
        y = y.astype(np.float64).ravel()
        y -= np.mean(y)
        y = y[isBg]
        b = np.ones_like(x, dtype=np.float64)

        M = np.vstack([b]).T  # order = 0
        if order == 1:
            M = np.vstack([b, x, y]).T
        elif order == 2:
            M = np.vstack([b, x, y, x**2., y**2., x*y]).T

        pars = np.linalg.lstsq(M, B)[0]
        return pars

    def makeStarModel(self, bbox, psf, xcen, ycen, flux):
        """!Generate model (2-d Image) of a 'star' (single PSF) centered at given coordinates

        @param bbox Bounding box marking pixel coordinates for generated model
        @param psf Psf model used to generate the 'star'
        @param xcen Desired x-centroid of the 'star'
        @param ycen Desired y-centroid of the 'star'
        @param flux Desired flux of the 'star'

        @return 2-d stellar `afwImage.Image` of width/height matching input `bbox`,
        containing PSF with given centroid and flux
        """

        # Generate the psf image, normalize to flux
        psf_img = psf.computeImage(afwGeom.Point2D(xcen, ycen)).convertF()
        psf_img_sum = np.nansum(psf_img.getArray())
        psf_img *= (flux/psf_img_sum)

        # Clip the PSF image bounding box to fall within the footprint bounding box
        psf_box = psf_img.getBBox()
        psf_box.clip(bbox)
        psf_img = afwImage.ImageF(psf_img, psf_box, afwImage.PARENT)

        # Then actually crop the psf image.
        # Usually not necessary, but if the dipole is near the edge of the image...
        # Would be nice if we could compare original pos_box with clipped pos_box and
        #     see if it actually was clipped.
        p_Im = afwImage.ImageF(bbox)
        tmpSubim = afwImage.ImageF(p_Im, psf_box, afwImage.PARENT)
        tmpSubim += psf_img

        return p_Im

    def makeModel(self, x, flux, xcenPos, ycenPos, xcenNeg, ycenNeg, fluxNeg=None,
                  b=None, x1=None, y1=None, xy=None, x2=None, y2=None,
                  bNeg=None, x1Neg=None, y1Neg=None, xyNeg=None, x2Neg=None, y2Neg=None,
                  **kwargs):
        """!Generate dipole model with given parameters.

        This is the function whose sum-of-squared difference from data
        is minimized by `lmfit`.

        @param x Input independent variable. Used here as the grid on
        which to compute the background gradient model.
        @param flux Desired flux of the positive lobe of the dipole
        @param xcenPos Desired x-centroid of the positive lobe of the dipole
        @param ycenPos Desired y-centroid of the positive lobe of the dipole
        @param xcenNeg Desired x-centroid of the negative lobe of the dipole
        @param ycenNeg Desired y-centroid of the negative lobe of the dipole
        @param fluxNeg Desired flux of the negative lobe of the dipole, set to 'flux' if None
        @param b, x1, y1, xy, x2, y2 Gradient parameters for positive lobe.
        @param bNeg, x1Neg, y1Neg, xyNeg, x2Neg, y2Neg Gradient parameters for negative lobe.
        They are set to the corresponding positive values if None.

        @param **kwargs Keyword arguments passed through `lmfit` and
        used by this function. These must include:
           - `psf` Psf model used to generate the 'star'
           - `rel_weight` Used to signify least-squares weighting of posImage/negImage
           relative to diffim. If `rel_weight == 0` then posImage/negImage are ignored.
           - `bbox` Bounding box containing region to be modelled

        @see `makeBackgroundModel` for further parameter descriptions.

        @return `numpy.array` of width/height matching input bbox,
        containing dipole model with given centroids and flux(es). If
        `rel_weight` = 0, this is a 2-d array with dimensions matching
        those of bbox; otherwise a stack of three such arrays,
        representing the dipole (diffim), positive and negative images
        respectively.
        """

        psf = kwargs.get('psf')
        rel_weight = kwargs.get('rel_weight')  # if > 0, we're including pre-sub. images
        fp = kwargs.get('footprint')
        bbox = fp.getBBox()

        if fluxNeg is None:
            fluxNeg = flux

        if self.debug:
            self.log.log(self.log.DEBUG, '%.2f %.2f %.2f %.2f %.2f %.2f' %
                         (flux, fluxNeg, xcenPos, ycenPos, xcenNeg, ycenNeg))
            if x1 is not None:
                self.log.log(self.log.DEBUG, '     %.2f %.2f %.2f' % (b, x1, y1))
            if xy is not None:
                self.log.log(self.log.DEBUG, '     %.2f %.2f %.2f' % (xy, x2, y2))

        posIm = self.makeStarModel(bbox, psf, xcenPos, ycenPos, flux)
        negIm = self.makeStarModel(bbox, psf, xcenNeg, ycenNeg, fluxNeg)

        in_x = x
        if in_x is None:  # use the footprint to generate the input grid
            y, x = np.mgrid[bbox.getBeginY():bbox.getEndY(), bbox.getBeginX():bbox.getEndX()]
            in_x = np.array([x, y]) * 1.
            in_x[0, :] -= in_x[0, :].mean()  # center it!
            in_x[1, :] -= in_x[1, :].mean()

        if b is not None:
            gradient = self.makeBackgroundModel(in_x, (b, x1, y1, xy, x2, y2))

            # If bNeg is None, then don't fit the negative background separately
            if bNeg is not None:
                gradientNeg = self.makeBackgroundModel(in_x, (bNeg, x1Neg, y1Neg, xyNeg, x2Neg, y2Neg))
            else:
                gradientNeg = gradient

            posIm.getArray()[:, :] += gradient
            negIm.getArray()[:, :] += gradientNeg

        # Generate the diffIm model
        diffIm = afwImage.ImageF(bbox)
        diffIm += posIm
        diffIm -= negIm

        zout = diffIm.getArray()
        if rel_weight > 0.:
            zout = np.append([zout], [posIm.getArray(), negIm.getArray()], axis=0)

        return zout


class DipoleFitAlgorithm(object):
    """!Lightweight class containing methods for fitting a dipole model in
    a diffim, used by DipoleFitPlugin.

    This code is documented in DMTN-007 (http://dmtn-007.lsst.io).

    Below is a (somewhat incomplete) list of improvements
    that would be worth investigating, given the time:

    @todo 1. evaluate necessity for separate parameters for pos- and neg- images
    @todo 2. only fit background OUTSIDE footprint (DONE) and dipole params INSIDE footprint (NOT DONE)?
    @todo 3. correct normalization of least-squares weights based on variance planes
    @todo 4. account for PSFs that vary across the exposures (should be happening by default?)
    @todo 5. correctly account for NA/masks  (i.e., ignore!)
    @todo 6. better exception handling in the plugin
    @todo 7. better classification of dipoles (e.g. by comparing chi2 fit vs. monopole?)
    @todo 8. (DONE) Initial fast estimate of background gradient(s) params -- perhaps using numpy.lstsq
    @todo 9. (NOT NEEDED - see (2)) Initial fast test whether a background gradient needs to be fit
    @todo 10. (DONE) better initial estimate for flux when there's a strong gradient
    @todo 11. (DONE) requires a new package `lmfit` -- investiate others? (astropy/scipy/iminuit?)
    """

    # This is just a private version number to sync with the ipython notebooks that I have been
    # using for algorithm development.
    _private_version_ = '0.0.5'

    def __init__(self, diffim, posImage=None, negImage=None):
        """!Algorithm to run dipole measurement on a diaSource

        @param diffim Exposure on which the diaSources were detected
        @param posImage "Positive" exposure from which the template was subtracted
        @param negImage "Negative" exposure which was subtracted from the posImage
        """

        self.diffim = diffim
        self.posImage = posImage
        self.negImage = negImage
        self.psfSigma = None
        if diffim is not None:
            self.psfSigma = diffim.getPsf().computeShape().getDeterminantRadius()

        self.log = pexLog.Log(pexLog.Log.getDefaultLog(), __name__, pexLog.Log.INFO)

        import lsstDebug
        self.debug = lsstDebug.Info(__name__).debug

    def fitDipoleImpl(self, source, tol=1e-7, rel_weight=0.5,
                      fitBackground=1, bgGradientOrder=1, maxSepInSigma=5.,
                      separateNegParams=True, verbose=False):
        """!Fit a dipole model to an input difference image.

        Actually, fits the subimage bounded by the input source's
        footprint) and optionally constrain the fit using the
        pre-subtraction images posImage and negImage.

        @return `lmfit.MinimizerResult` object containing the fit
        parameters and other information.

        @see `fitDipole()`
        """

        # Only import lmfit if someone wants to use the new DipoleFitAlgorithm.
        import lmfit

        fp = source.getFootprint()
        bbox = fp.getBBox()
        subim = afwImage.MaskedImageF(self.diffim.getMaskedImage(), bbox, afwImage.PARENT)

        z = diArr = subim.getArrays()[0]
        weights = 1. / subim.getArrays()[2]  # get the weights (=1/variance)

        if rel_weight > 0. and ((self.posImage is not None) or (self.negImage is not None)):
            if self.negImage is not None:
                negSubim = afwImage.MaskedImageF(self.negImage.getMaskedImage(), bbox, afwImage.PARENT)
            if self.posImage is not None:
                posSubim = afwImage.MaskedImageF(self.posImage.getMaskedImage(), bbox, afwImage.PARENT)
            if self.posImage is None:  # no science image provided; generate it from diffim + negImage
                posSubim = subim.clone()
                posSubim += negSubim
            if self.negImage is None:  # no template provided; generate it from the posImage - diffim
                negSubim = posSubim.clone()
                negSubim -= subim

            z = np.append([z], [posSubim.getArrays()[0],
                                negSubim.getArrays()[0]], axis=0)
            # Weight the pos/neg images by rel_weight relative to the diffim
            weights = np.append([weights], [1. / posSubim.getArrays()[2] * rel_weight,
                                            1. / negSubim.getArrays()[2] * rel_weight], axis=0)
        else:
            rel_weight = 0.  # a short-cut for "don't include the pre-subtraction data"

        # It seems that `lmfit` requires a static functor as its optimized method, which eliminates
        # the ability to pass a bound method or other class method. Here we write a wrapper which
        # makes this possible.
        def dipoleModelFunctor(x, flux, xcenPos, ycenPos, xcenNeg, ycenNeg, fluxNeg=None,
                               b=None, x1=None, y1=None, xy=None, x2=None, y2=None,
                               bNeg=None, x1Neg=None, y1Neg=None, xyNeg=None, x2Neg=None, y2Neg=None,
                               **kwargs):
            """!Generate dipole model with given parameters.

            It simply defers to `modelObj.makeModel()`, where `modelObj` comes
            out of `kwargs['modelObj']`.

            @see DipoleModel.makeModel
            """
            modelObj = kwargs.pop('modelObj')
            return modelObj.makeModel(x, flux, xcenPos, ycenPos, xcenNeg, ycenNeg, fluxNeg=fluxNeg,
                                      b=b, x1=x1, y1=y1, xy=xy, x2=x2, y2=y2,
                                      bNeg=bNeg, x1Neg=x1Neg, y1Neg=y1Neg, xyNeg=xyNeg,
                                      x2Neg=x2Neg, y2Neg=y2Neg, **kwargs)

        dipoleModel = DipoleModel()

        modelFunctor = dipoleModelFunctor  # dipoleModel.makeModel does not work for now.
        # Create the lmfit model (lmfit uses scipy 'leastsq' option by default - Levenberg-Marquardt)
        # Note we can also tell it to drop missing values from the data.
        gmod = lmfit.Model(modelFunctor, verbose=verbose, missing='drop')
        # independent_vars=independent_vars) #, param_names=param_names)

        # Add the constraints for centroids, fluxes.
        # starting constraint - near centroid of footprint
        fpCentroid = np.array([fp.getCentroid().getX(), fp.getCentroid().getY()])
        cenNeg = cenPos = fpCentroid

        pks = fp.getPeaks()
        if len(pks) >= 1:
            cenPos = pks[0].getF()    # if individual (merged) peaks were detected, use those
        if len(pks) >= 2:
            cenNeg = pks[1].getF()

        # For close/faint dipoles the starting locs (min/max) might be way off, let's help them a bit.
        # First assume dipole is not separated by more than 5*psfSigma.
        maxSep = self.psfSigma * maxSepInSigma

        # As an initial guess -- assume the dipole is close to the center of the footprint.
        if np.sum(np.sqrt((np.array(cenPos) - fpCentroid)**2.)) > maxSep:
            cenPos = fpCentroid
        if np.sum(np.sqrt((np.array(cenNeg) - fpCentroid)**2.)) > maxSep:
            cenPos = fpCentroid

        # parameter hints/constraints: https://lmfit.github.io/lmfit-py/model.html#model-param-hints-section
        # might make sense to not use bounds -- see http://lmfit.github.io/lmfit-py/bounds.html
        # also see this discussion -- https://github.com/scipy/scipy/issues/3129
        gmod.set_param_hint('xcenPos', value=cenPos[0],
                            min=cenPos[0]-maxSep, max=cenPos[0]+maxSep)
        gmod.set_param_hint('ycenPos', value=cenPos[1],
                            min=cenPos[1]-maxSep, max=cenPos[1]+maxSep)
        gmod.set_param_hint('xcenNeg', value=cenNeg[0],
                            min=cenNeg[0]-maxSep, max=cenNeg[0]+maxSep)
        gmod.set_param_hint('ycenNeg', value=cenNeg[1],
                            min=cenNeg[1]-maxSep, max=cenNeg[1]+maxSep)

        # Use the (flux under the dipole)*5 for an estimate.
        # Lots of testing showed that having startingFlux be too high was better than too low.
        startingFlux = np.nansum(np.abs(diArr) - np.nanmedian(np.abs(diArr))) * 5.
        posFlux = negFlux = startingFlux

        # TBD: set max. flux limit?
        gmod.set_param_hint('flux', value=posFlux, min=0.1)

        if separateNegParams:
            # TBD: set max negative lobe flux limit?
            gmod.set_param_hint('fluxNeg', value=np.abs(negFlux), min=0.1)

        # Fixed parameters (don't fit for them if there are no pre-sub images or no gradient fit requested):
        # Right now (fitBackground == 1), we fit a linear model to the background and then subtract
        # it from the data and then don't fit the background again (this is faster).
        # A slower alternative (fitBackground == 2) is to use the estimated background parameters as
        # starting points in the integrated model fit. That is currently not performed by default,
        # but might be desirable in some cases.
        bgParsPos = bgParsNeg = (0., 0., 0.)
        if ((rel_weight > 0.) and (fitBackground != 0) and (bgGradientOrder >= 0)):
            pbg = 0.
            bgFitImage = self.posImage if self.posImage is not None else self.negImage
            # Fit the gradient to the background (linear model)
            bgParsPos = bgParsNeg = dipoleModel.fitFootprintBackground(source, bgFitImage,
                                                                       order=bgGradientOrder)

            # Generate the gradient and subtract it from the pre-subtraction image data
            if fitBackground == 1:
                in_x = dipoleModel._generateXYGrid(bbox)
                pbg = dipoleModel.makeBackgroundModel(in_x, tuple(bgParsPos))
                z[1, :] -= pbg
                z[1, :] -= np.nanmedian(z[1, :])
                posFlux = np.nansum(z[1, :])
                gmod.set_param_hint('flux', value=posFlux*1.5, min=0.1)

                if separateNegParams and self.negImage is not None:
                    bgParsNeg = dipoleModel.fitFootprintBackground(source, self.negImage,
                                                                   order=bgGradientOrder)
                    pbg = dipoleModel.makeBackgroundModel(in_x, tuple(bgParsNeg))
                z[2, :] -= pbg
                z[2, :] -= np.nanmedian(z[2, :])
                if separateNegParams:
                    negFlux = np.nansum(z[2, :])
                    gmod.set_param_hint('fluxNeg', value=negFlux*1.5, min=0.1)

            # Do not subtract the background from the images but include the background parameters in the fit
            if fitBackground == 2:
                if bgGradientOrder >= 0:
                    gmod.set_param_hint('b', value=bgParsPos[0])
                    if separateNegParams:
                        gmod.set_param_hint('bNeg', value=bgParsNeg[0])
                if bgGradientOrder >= 1:
                    gmod.set_param_hint('x1', value=bgParsPos[1])
                    gmod.set_param_hint('y1', value=bgParsPos[2])
                    if separateNegParams:
                        gmod.set_param_hint('x1Neg', value=bgParsNeg[1])
                        gmod.set_param_hint('y1Neg', value=bgParsNeg[2])
                if bgGradientOrder >= 2:
                    gmod.set_param_hint('xy', value=bgParsPos[3])
                    gmod.set_param_hint('x2', value=bgParsPos[4])
                    gmod.set_param_hint('y2', value=bgParsPos[5])
                    if separateNegParams:
                        gmod.set_param_hint('xyNeg', value=bgParsNeg[3])
                        gmod.set_param_hint('x2Neg', value=bgParsNeg[4])
                        gmod.set_param_hint('y2Neg', value=bgParsNeg[5])

        y, x = np.mgrid[bbox.getBeginY():bbox.getEndY(), bbox.getBeginX():bbox.getEndX()]
        in_x = np.array([x, y]).astype(np.float)
        in_x[0, :] -= in_x[0, :].mean()  # center it!
        in_x[1, :] -= in_x[1, :].mean()

        # Instead of explicitly using a mask to ignore flagged pixels, just set the ignored pixels'
        #  weights to 0 in the fit. TBD: need to inspect mask planes to set this mask.
        mask = np.ones_like(z, dtype=bool)  # TBD: set mask values to False if the pixels are to be ignored

        # I'm not sure about the variance planes in the diffim (or convolved pre-sub. images
        # for that matter) so for now, let's just do an un-weighted least-squares fit
        # (override weights computed above).
        weights = mask.astype(np.float64)
        if self.posImage is not None and rel_weight > 0.:
            weights = np.array([np.ones_like(diArr), np.ones_like(diArr)*rel_weight,
                                np.ones_like(diArr)*rel_weight])

        # Set the weights to zero if mask is False
        if np.any(~mask):
            weights[~mask] = 0.

        # Note that although we can, we're not required to set initial values for params here,
        # since we set their param_hint's above.
        # Can add "method" param to not use 'leastsq' (==levenberg-marquardt), e.g. "method='nelder'"
        result = gmod.fit(z, weights=weights, x=in_x,
                          verbose=verbose,
                          fit_kws={'ftol': tol, 'xtol': tol, 'gtol': tol, 'maxfev': 250},  # see scipy docs
                          psf=self.diffim.getPsf(),  # hereon: kwargs that get passed to genDipoleModel()
                          rel_weight=rel_weight,
                          footprint=fp,
                          modelObj=dipoleModel)

        if verbose:  # the ci_report() seems to fail if neg params are constrained -- TBD why.
            # Never wanted in production - this takes a long time (longer than the fit!)
            # This is how to get confidence intervals out:
            #    https://lmfit.github.io/lmfit-py/confidence.html and
            #    http://cars9.uchicago.edu/software/python/lmfit/model.html
            print(result.fit_report(show_correl=False))
            if separateNegParams:
                print(result.ci_report())

        return result

    def fitDipole(self, source, tol=1e-7, rel_weight=0.1,
                  fitBackground=1, maxSepInSigma=5., separateNegParams=True,
                  bgGradientOrder=1, verbose=False, display=False):
        """!Wrapper around `fitDipoleImpl()` which performs the fit of a dipole
        model to an input diaSource.

        Actually, fits the subimage bounded by the input source's
        footprint) and optionally constrain the fit using the
        pre-subtraction images self.posImage (science) and
        self.negImage (template). Wraps the output into a
        `pipeBase.Struct` named tuple after computing additional
        statistics such as orientation and SNR.

        @param source Record containing the (merged) dipole source footprint detected on the diffim
        @param tol Tolerance parameter for scipy.leastsq() optimization
        @param rel_weight Weighting of posImage/negImage relative to the diffim in the fit
        @param fitBackground How to fit linear background gradient in posImage/negImage (see notes)
        @param bgGradientOrder Desired polynomial order of background gradient (allowed are [0,1,2])
        @param maxSepInSigma Allowed window of centroid parameters relative to peak in input source footprint
        @param separateNegParams Fit separate parameters to the flux and background gradient in
        the negative images? If true, this adds a separate parameter for the negative flux, and [1, 3, or 6]
        additional parameters to fit for the background gradient in the negImage. Otherwise, the flux and
        gradient parameters are constrained to be exactly equal in the fit.
        @param verbose Be verbose
        @param display Display input data, best fit model(s) and residuals in a matplotlib window.

        @return `pipeBase.Struct` object containing the fit parameters and other information.
        @return `lmfit.MinimizerResult` object for debugging and error estimation, etc.

        @note Parameter `fitBackground` has three options, thus it is an integer:
        - 0: do not fit background at all
        - 1 (default): pre-fit the background using linear least squares and then do not fit it as part
            of the dipole fitting optimization
        - 2: pre-fit the background using linear least squares (as in 1), and use the parameter
            estimates from that fit as starting parameters for an integrated "re-fit" of the background
            as part of the overall dipole fitting optimization.
        """

        fitResult = self.fitDipoleImpl(
            source, tol=tol, rel_weight=rel_weight, fitBackground=fitBackground,
            maxSepInSigma=maxSepInSigma, separateNegParams=separateNegParams,
            bgGradientOrder=bgGradientOrder, verbose=verbose)

        # Display images, model fits and residuals (currently uses matplotlib display functions)
        if display:
            fp = source.getFootprint()
            self.displayFitResults(fp, fitResult)

        fitParams = fitResult.best_values
        if fitParams['flux'] <= 1.:   # usually around 0.1 -- the minimum flux allowed -- i.e. bad fit.
            out = Struct(posCentroidX=np.nan, posCentroidY=np.nan,
                         negCentroidX=np.nan, negCentroidY=np.nan,
                         posFlux=np.nan, negFlux=np.nan, posFluxSigma=np.nan, negFluxSigma=np.nan,
                         centroidX=np.nan, centroidY=np.nan, orientation=np.nan,
                         signalToNoise=np.nan, chi2=np.nan, redChi2=np.nan)
            return out, fitResult

        centroid = ((fitParams['xcenPos'] + fitParams['xcenNeg']) / 2.,
                    (fitParams['ycenPos'] + fitParams['ycenNeg']) / 2.)
        dx, dy = fitParams['xcenPos'] - fitParams['xcenNeg'], fitParams['ycenPos'] - fitParams['ycenNeg']
        angle = np.arctan2(dy, dx) / np.pi * 180.   # convert to degrees (should keep as rad?)

        # Exctract flux value, compute signalToNoise from flux/variance_within_footprint
        # Also extract the stderr of flux estimate.
        def computeSumVariance(exposure, footprint):
            box = footprint.getBBox()
            subim = afwImage.MaskedImageF(exposure.getMaskedImage(), box, afwImage.PARENT)
            return np.sqrt(np.nansum(subim.getArrays()[1][:, :]))

        fluxVal = fluxVar = fitParams['flux']
        fluxErr = fluxErrNeg = fitResult.params['flux'].stderr
        if self.posImage is not None:
            fluxVar = computeSumVariance(self.posImage, source.getFootprint())
        else:
            fluxVar = computeSumVariance(self.diffim, source.getFootprint())

        fluxValNeg, fluxVarNeg = fluxVal, fluxVar
        if separateNegParams:
            fluxValNeg = fitParams['fluxNeg']
            fluxErrNeg = fitResult.params['fluxNeg'].stderr
        if self.negImage is not None:
            fluxVarNeg = computeSumVariance(self.negImage, source.getFootprint())

        try:
            signalToNoise = np.sqrt((fluxVal/fluxVar)**2 + (fluxValNeg/fluxVarNeg)**2)
        except:  # catch divide by zero - should never happen.
            signalToNoise = np.nan

        out = Struct(posCentroidX=fitParams['xcenPos'], posCentroidY=fitParams['ycenPos'],
                     negCentroidX=fitParams['xcenNeg'], negCentroidY=fitParams['ycenNeg'],
                     posFlux=fluxVal, negFlux=-fluxValNeg, posFluxSigma=fluxErr, negFluxSigma=fluxErrNeg,
                     centroidX=centroid[0], centroidY=centroid[1], orientation=angle,
                     signalToNoise=signalToNoise, chi2=fitResult.chisqr, redChi2=fitResult.redchi)

        # fitResult may be returned for debugging
        return out, fitResult

    def displayFitResults(self, footprint, result):
        """!Display data, model fits and residuals (currently uses matplotlib display functions).

        @param footprint Footprint containing the dipole that was fit
        @param result `lmfit.MinimizerResult` object returned by `lmfit` optimizer
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError as err:
            log = pexLog.Log(pexLog.getDefaultLog(), __name__, pexLog.INFO)
            log.warn('Unable to import matplotlib: %s' % err)
            raise err

        def display2dArray(arr, title='Data', extent=None):
            """!Use `matplotlib.pyplot.imshow` to display a 2-D array with a given coordinate range.
            """
            fig = plt.imshow(arr, origin='lower', interpolation='none', cmap='gray', extent=extent)
            plt.title(title)
            plt.colorbar(fig, cmap='gray')
            return fig

        z = result.data
        fit = result.best_fit
        bbox = footprint.getBBox()
        extent = (bbox.getBeginX(), bbox.getEndX(), bbox.getBeginY(), bbox.getEndY())
        if z.shape[0] == 3:
            fig = plt.figure(figsize=(8, 8))
            for i in range(3):
                plt.subplot(3, 3, i*3+1)
                display2dArray(z[i, :], 'Data', extent=extent)
                plt.subplot(3, 3, i*3+2)
                display2dArray(fit[i, :], 'Model', extent=extent)
                plt.subplot(3, 3, i*3+3)
                display2dArray(z[i, :] - fit[i, :], 'Residual', extent=extent)
            return fig
        else:
            fig = plt.figure(figsize=(8, 2.5))
            plt.subplot(1, 3, 1)
            display2dArray(z, 'Data', extent=extent)
            plt.subplot(1, 3, 2)
            display2dArray(fit, 'Model', extent=extent)
            plt.subplot(1, 3, 3)
            display2dArray(z - fit, 'Residual', extent=extent)
            return fig

        plt.show()


@measBase.register("ip_diffim_DipoleFit")
class DipoleFitPlugin(measBase.SingleFramePlugin):
    """!Subclass of SingleFramePlugin which fits dipoles to all merged (two-peak) diaSources

    Accepts up to three input images in its `measure` method. If these are
    provided, it includes data from the pre-subtraction posImage
    (science image) and optionally negImage (template image) to
    constrain the fit. The meat of the fitting routines are in the
    class DipoleFitAlgorithm.

    The motivation behind this plugin and the necessity for including more than
    one exposure are documented in DMTN-007 (http://dmtn-007.lsst.io).

    This class is named `ip_diffim_DipoleFit` so that it may be used alongside
    the existing `ip_diffim_DipoleMeasurement` classes until such a time as those
    are deemed to be replaceable by this.
    """

    ConfigClass = DipoleFitPluginConfig
    DipoleFitAlgorithmClass = DipoleFitAlgorithm  # Pointer to the class that performs the fit

    FAILURE_EDGE = 1   # too close to the edge
    FAILURE_FIT = 2    # failure in the fitting
    FAILURE_NOT_DIPOLE = 4  # input source is not a putative dipole to begin with

    @classmethod
    def getExecutionOrder(cls):
        """!Set execution order to `FLUX_ORDER`.

        This includes algorithms that require both `getShape()` and `getCentroid()`,
        in addition to a Footprint and its Peaks.
        """
        return cls.FLUX_ORDER

    def __init__(self, config, name, schema, metadata):
        measBase.SingleFramePlugin.__init__(self, config, name, schema, metadata)

        self.log = pexLog.Log(pexLog.Log.getDefaultLog(), name, pexLog.Log.INFO)

        self._setupSchema(config, name, schema, metadata)

    def _setupSchema(self, config, name, schema, metadata):
        # Get a FunctorKey that can quickly look up the "blessed" centroid value.
        self.centroidKey = afwTable.Point2DKey(schema["slot_Centroid"])

        # Add some fields for our outputs, and save their Keys.
        # Use setattr() to programmatically set the pos/neg named attributes to values, e.g.
        # self.posCentroidKeyX = 'ip_diffim_DipoleFit_pos_centroid_x'

        for pos_neg in ['pos', 'neg']:

            key = schema.addField(
                schema.join(name, pos_neg, "flux"), type=float, units="count",
                doc="Dipole {0} lobe flux".format(pos_neg))
            setattr(self, ''.join((pos_neg, 'FluxKey')), key)

            key = schema.addField(
                schema.join(name, pos_neg, "fluxSigma"), type=float, units="pixel",
                doc="1-sigma uncertainty for {0} dipole flux".format(pos_neg))
            setattr(self, ''.join((pos_neg, 'FluxSigmaKey')), key)

            for x_y in ['x', 'y']:
                key = schema.addField(
                    schema.join(name, pos_neg, "centroid", x_y), type=float, units="pixel",
                    doc="Dipole {0} lobe centroid".format(pos_neg))
                setattr(self, ''.join((pos_neg, 'CentroidKey', x_y.upper())), key)

        for x_y in ['x', 'y']:
            key = schema.addField(
                schema.join(name, "centroid", x_y), type=float, units="pixel",
                doc="Dipole centroid")
            setattr(self, ''.join(('centroidKey', x_y.upper())), key)

        self.fluxKey = schema.addField(
            schema.join(name, "flux"), type=float, units="count",
            doc="Dipole overall flux")

        self.orientationKey = schema.addField(
            schema.join(name, "orientation"), type=float, units="deg",
            doc="Dipole orientation")

        self.separationKey = schema.addField(
            schema.join(name, "separation"), type=float, units="pixel",
            doc="Pixel separation between positive and negative lobes of dipole")

        self.chi2dofKey = schema.addField(
            schema.join(name, "chi2dof"), type=float,
            doc="Chi2 per degree of freedom of dipole fit")

        self.signalToNoiseKey = schema.addField(
            schema.join(name, "signalToNoise"), type=float,
            doc="Estimated signal-to-noise of dipole fit")

        self.classificationFlagKey = schema.addField(
            schema.join(name, "flag", "classification"), type="Flag",
            doc="Flag indicating diaSource is classified as a dipole")

        self.flagKey = schema.addField(
            schema.join(name, "flag"), type="Flag",
            doc="General failure flag for dipole fit")

        self.edgeFlagKey = schema.addField(
            schema.join(name, "flag", "edge"), type="Flag",
            doc="Flag set when dipole is too close to edge of image")

    def measure(self, measRecord, exposure, posExp=None, negExp=None):
        """!Perform the non-linear least squares minimization on the putative dipole source.

        @param measRecord   diaSources that will be measured using dipole measurement
        @param exposure  Difference exposure on which the diaSources were detected; `exposure = posExp-negExp`
        @param posExp    "Positive" exposure, typically a science exposure, or None if unavailable
        @param negExp    "Negative" exposure, typically a template exposure, or None if unavailable

        @note When `posExp` is `None`, will compute `posImage = exposure + negExp`.
        Likewise, when `negExp` is `None`, will compute `negImage = posExp - exposure`.
        If both `posExp` and `negExp` are `None`, will attempt to fit the dipole to just the `exposure`
        with no constraint.

        The main functionality of this routine was placed outside of
        this plugin (into `DipoleFitAlgorithm.fitDipole()`) so that
        `DipoleFitAlgorithm.fitDipole()` can be called separately for
        testing (@see `tests/testDipoleFitter.py`)
        """

        pks = measRecord.getFootprint().getPeaks()
        if len(pks) <= 1:  # not a dipole for our analysis
            self.fail(measRecord, measBase.MeasurementError('not a dipole', self.FAILURE_NOT_DIPOLE))

        result = None
        try:
            alg = self.DipoleFitAlgorithmClass(exposure, posImage=posExp, negImage=negExp)
            result, _ = alg.fitDipole(
                measRecord, rel_weight=self.config.relWeight,
                tol=self.config.tolerance,
                maxSepInSigma=self.config.maxSeparation,
                fitBackground=self.config.fitBackground,
                separateNegParams=self.config.fitSeparateNegParams,
                verbose=False, display=False)
        except pexExcept.LengthError:
            self.fail(measRecord, measBase.MeasurementError('edge failure', self.FAILURE_EDGE))
        except Exception:
            self.fail(measRecord, measBase.MeasurementError('dipole fit failure', self.FAILURE_FIT))

        if result is None:
            return result

        self.log.log(self.log.DEBUG, "Dipole fit result: %d %s" % (measRecord.getId(), str(result)))

        if result.posFlux <= 1.:   # usually around 0.1 -- the minimum flux allowed -- i.e. bad fit.
            self.fail(measRecord, measBase.MeasurementError('dipole fit failure', self.FAILURE_FIT))

        # add chi2, coord/flux uncertainties (TBD), dipole classification

        # Add the relevant values to the measRecord
        measRecord[self.posFluxKey] = result.posFlux
        measRecord[self.posFluxSigmaKey] = result.signalToNoise   # to be changed to actual sigma!
        measRecord[self.posCentroidKeyX] = result.posCentroidX
        measRecord[self.posCentroidKeyY] = result.posCentroidY

        measRecord[self.negFluxKey] = result.negFlux
        measRecord[self.negFluxSigmaKey] = result.signalToNoise   # to be changed to actual sigma!
        measRecord[self.negCentroidKeyX] = result.negCentroidX
        measRecord[self.negCentroidKeyY] = result.negCentroidY

        # Dia source flux: average of pos+neg
        measRecord[self.fluxKey] = (abs(result.posFlux) + abs(result.negFlux))/2.
        measRecord[self.orientationKey] = result.orientation
        measRecord[self.separationKey] = np.sqrt((result.posCentroidX - result.negCentroidX)**2. +
                                                 (result.posCentroidY - result.negCentroidY)**2.)
        measRecord[self.centroidKeyX] = result.centroidX
        measRecord[self.centroidKeyY] = result.centroidY

        measRecord[self.signalToNoiseKey] = result.signalToNoise
        measRecord[self.chi2dofKey] = result.redChi2

        self.doClassify(measRecord, result.chi2)

    def doClassify(self, measRecord, chi2val):
        """!Determine if source is classified as dipole via three criteria:
        - does the total signal-to-noise surpass the minSn?
        - are the pos/neg fluxes greater than 1.0 and no more than 0.65 (param `maxFluxRatio`)
            of the total flux? By default this will never happen since `posFlux == negFlux`.
        - is it a good fit (`chi2dof` < 1)? (Currently not used.)
        """

        # First, does the total signal-to-noise surpass the minSn?
        passesSn = measRecord[self.signalToNoiseKey] > self.config.minSn

        # Second, are the pos/neg fluxes greater than 1.0 and no more than 0.65 (param maxFluxRatio)
        # of the total flux? By default this will never happen since posFlux = negFlux.
        passesFluxPos = (abs(measRecord[self.posFluxKey]) /
                         (measRecord[self.fluxKey]*2.)) < self.config.maxFluxRatio
        passesFluxPos &= (abs(measRecord[self.posFluxKey]) >= 1.0)
        passesFluxNeg = (abs(measRecord[self.negFluxKey]) /
                         (measRecord[self.fluxKey]*2.)) < self.config.maxFluxRatio
        passesFluxNeg &= (abs(measRecord[self.negFluxKey]) >= 1.0)
        allPass = (passesSn and passesFluxPos and passesFluxNeg)  # and passesChi2)

        # Third, is it a good fit (chi2dof < 1)?
        # Use scipy's chi2 cumulative distrib to estimate significance
        # This doesn't really work since I don't trust the values in the variance plane (which
        #   affects the least-sq weights, which affects the resulting chi2).
        # But I'm going to keep this here for future use.
        if False:
            from scipy.stats import chi2
            ndof = chi2val / measRecord[self.chi2dofKey]
            significance = chi2.cdf(chi2val, ndof)
            passesChi2 = significance < self.config.maxChi2DoF
            allPass = allPass and passesChi2

        if allPass:  # Note cannot pass `allPass` into the `measRecord.set()` call below...?
            measRecord.set(self.classificationFlagKey, True)
        else:
            measRecord.set(self.classificationFlagKey, False)

    def fail(self, measRecord, error=None):
        """!Catch failures and set the correct flags.
        """

        measRecord.set(self.flagKey, True)
        if error is not None:
            if error.getFlagBit() == self.FAILURE_EDGE:
                self.log.warn('DipoleFitPlugin not run on record %d: %s' % (measRecord.getId(), str(error)))
                measRecord.set(self.edgeFlagKey, True)
            if error.getFlagBit() == self.FAILURE_FIT:
                self.log.warn('DipoleFitPlugin failed on record %d: %s' % (measRecord.getId(), str(error)))
                measRecord.set(self.flagKey, True)
            if error.getFlagBit() == self.FAILURE_NOT_DIPOLE:
                self.log.warn('DipoleFitPlugin not run on record %d: %s' % (measRecord.getId(), str(error)))
                measRecord.set(self.flagKey, True)
        else:
            self.log.warn('DipoleFitPlugin failed on record %d' % measRecord.getId())