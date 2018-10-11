# This file is part of ip_diffim.
#
# LSST Data Management System
# This product includes software developed by the
# LSST Project (http://www.lsst.org/).
# See COPYRIGHT file at the top of the source tree.
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

from astropy import units as u
import numpy as np
from scipy import ndimage
import unittest

from lsst.afw.coord import Observatory, Weather
import lsst.afw.geom as afwGeom
import lsst.afw.image as afwImage
import lsst.afw.math as afwMath
from lsst.geom import arcseconds, degrees, radians
from lsst.ip.diffim.dcrModel import DcrModel, calculateDcr, calculateImageParallacticAngle, applyDcr
from lsst.meas.algorithms.testUtils import plantSources
import lsst.utils.tests


class DcrModelTestTask(lsst.utils.tests.TestCase):
    """A test case for the DCR-aware image coaddition algorithm.

    Attributes
    ----------
    bbox : `lsst.afw.geom.Box2I`
        Bounding box of the test model.
    bufferSize : `int`
        Distance from the inner edge of the bounding box
        to avoid placing test sources in the model images.
    dcrNumSubfilters : int
        Number of sub-filters used to model chromatic effects within a band.
    lambdaEff : `float`
        Effective wavelength of the full band.
    lambdaMax : `float`
        Maximum wavelength where the relative throughput
        of the band is greater than 1%.
    lambdaMin : `float`
        Minimum wavelength where the relative throughput
        of the band is greater than 1%.
    mask : `lsst.afw.image.Mask`
        Reference mask of the unshifted model.
    """

    def setUp(self):
        """Define the filter, DCR parameters, and the bounding box for the tests.
        """
        self.rng = np.random.RandomState(5)
        self.nRandIter = 10  # Number of iterations to repeat each test with random numbers.
        self.dcrNumSubfilters = 3
        self.lambdaEff = 476.31  # Use LSST g band values for the test.
        self.lambdaMin = 405.
        self.lambdaMax = 552.
        self.bufferSize = 5
        xSize = 40
        ySize = 42
        x0 = 12345
        y0 = 67890
        self.bbox = afwGeom.Box2I(afwGeom.Point2I(x0, y0), afwGeom.Extent2I(xSize, ySize))

    def makeTestImages(self, seed=5, nSrc=5, psfSize=2., noiseLevel=5.,
                       detectionSigma=5., sourceSigma=20., fluxRange=2.):
        """Make reproduceable PSF-convolved masked images for testing.

        Parameters
        ----------
        seed : `int`, optional
            Seed value to initialize the random number generator.
        nSrc : `int`, optional
            Number of sources to simulate.
        psfSize : `float`, optional
            Width of the PSF of the simulated sources, in pixels.
        noiseLevel : `float`, optional
            Standard deviation of the noise to add to each pixel.
        detectionSigma : `float`, optional
            Threshold amplitude of the image to set the "DETECTED" mask.
        sourceSigma : `float`, optional
            Average amplitude of the simulated sources,
            relative to ``noiseLevel``
        fluxRange : `float`, optional
            Range in flux amplitude of the simulated sources.

        Returns
        -------
        modelImages : `list` of `lsst.afw.image.maskedImage`
            A list of masked images, each containing the model for one subfilter
        """
        rng = np.random.RandomState(seed)
        x0, y0 = self.bbox.getBegin()
        xSize, ySize = self.bbox.getDimensions()
        xLoc = rng.rand(nSrc)*(xSize - 2*self.bufferSize) + self.bufferSize + x0
        yLoc = rng.rand(nSrc)*(ySize - 2*self.bufferSize) + self.bufferSize + y0
        modelImages = []

        imageSum = np.zeros((ySize, xSize))
        for subfilter in range(self.dcrNumSubfilters):
            flux = (rng.rand(nSrc)*(fluxRange - 1.) + 1.)*sourceSigma*noiseLevel
            sigmas = [psfSize for src in range(nSrc)]
            coordList = list(zip(xLoc, yLoc, flux, sigmas))
            model = plantSources(self.bbox, 10, 0, coordList, addPoissonNoise=False)
            model.image.array += rng.rand(ySize, xSize)*noiseLevel
            imageSum += model.image.array
            model.mask.addMaskPlane("CLIPPED")
            modelImages.append(model.maskedImage)
        maskVals = np.zeros_like(imageSum)
        maskVals[imageSum > detectionSigma*noiseLevel] = afwImage.Mask.getPlaneBitMask('DETECTED')
        for model in modelImages:
            model.mask.array[:] = maskVals
        self.mask = modelImages[0].mask
        return modelImages

    def makeDummyWcs(self, rotAngle, pixelScale, crval, flipX=True):
        """Make a World Coordinate System object for testing.

        Parameters
        ----------
        rotAngle : `lsst.geom.Angle`
            rotation of the CD matrix, East from North
        pixelScale : `lsst.geom.Angle`
            Pixel scale of the projection.
        crval : `lsst.afw.geom.SpherePoint`
            Coordinates of the reference pixel of the wcs.
        flipX : `bool`, optional
            Flip the direction of increasing Right Ascension.

        Returns
        -------
        `lsst.afw.geom.skyWcs.SkyWcs`
            A wcs that matches the inputs.
        """
        crpix = afwGeom.Box2D(self.bbox).getCenter()
        cdMatrix = afwGeom.makeCdMatrix(scale=pixelScale, orientation=rotAngle, flipX=flipX)
        wcs = afwGeom.makeSkyWcs(crpix=crpix, crval=crval, cdMatrix=cdMatrix)
        return wcs

    def makeDummyVisitInfo(self, azimuth, elevation):
        """Make a self-consistent visitInfo object for testing.

        For simplicity, the simulated observation is assumed
        to be taken on the local meridian.

        Parameters
        ----------
        azimuth : `lsst.geom.Angle`
            Azimuth angle of the simulated observation.
        elevation : `lsst.geom.Angle`
            Elevation angle of the simulated observation.

        Returns
        -------
        `lsst.afw.image.VisitInfo`
            VisitInfo for the exposure.
        """
        lsstLat = -30.244639*degrees
        lsstLon = -70.749417*degrees
        lsstAlt = 2663.
        lsstTemperature = 20.*u.Celsius  # in degrees Celcius
        lsstHumidity = 40.  # in percent
        lsstPressure = 73892.*u.pascal
        lsstWeather = Weather(lsstTemperature.value, lsstPressure.value, lsstHumidity)
        lsstObservatory = Observatory(lsstLon, lsstLat, lsstAlt)
        airmass = 1.0/np.sin(elevation.asRadians())
        era = 0.*radians  # on the meridian
        zenithAngle = 90.*degrees - elevation
        ra = lsstLon + np.sin(azimuth.asRadians())*zenithAngle/np.cos(lsstLat.asRadians())
        dec = lsstLat + np.cos(azimuth.asRadians())*zenithAngle
        visitInfo = afwImage.VisitInfo(era=era,
                                       boresightRaDec=afwGeom.SpherePoint(ra, dec),
                                       boresightAzAlt=afwGeom.SpherePoint(azimuth, elevation),
                                       boresightAirmass=airmass,
                                       boresightRotAngle=0.*radians,
                                       observatory=lsstObservatory,
                                       weather=lsstWeather
                                       )
        return visitInfo

    def testDummyVisitInfo(self):
        """Verify the implementation of the visitInfo used for tests.
        """
        azimuth = 0*degrees
        for testIter in range(self.nRandIter):
            elevation = (45. + self.rng.rand()*40.)*degrees  # Restrict to 45 < elevation < 85 degrees
            visitInfo = self.makeDummyVisitInfo(azimuth, elevation)
            dec = visitInfo.getBoresightRaDec().getLatitude().asRadians()
            lat = visitInfo.getObservatory().getLatitude().asRadians()
            # An observation made with azimuth=0 should be pointed to the North
            # So the RA should be North of the telescope's latitude
            self.assertGreater(dec, lat)
            parAngle = visitInfo.getBoresightParAngle()
            # If the observation is North of the telescope's latitude, the
            # direction to zenith should be along the -y axis
            # with a parallactic angle of 180 degrees
            self.assertAnglesAlmostEqual(parAngle, 180*degrees)

    def testDcrCalculation(self):
        """Test that the shift in pixels due to DCR is consistently computed.

        The shift is compared to pre-computed values.
        """
        dcrNumSubfilters = 3
        afwImage.utils.defineFilter("gTest", self.lambdaEff,
                                    lambdaMin=self.lambdaMin, lambdaMax=self.lambdaMax)
        filterInfo = afwImage.Filter("gTest")
        rotAngle = 0.*degrees
        azimuth = 30.*degrees
        elevation = 65.*degrees
        pixelScale = 0.2*arcseconds
        visitInfo = self.makeDummyVisitInfo(azimuth, elevation)
        wcs = self.makeDummyWcs(rotAngle, pixelScale, crval=visitInfo.getBoresightRaDec())
        dcrShift = calculateDcr(visitInfo, wcs, filterInfo, dcrNumSubfilters)
        # Compare to precomputed values.
        refShift = [afwGeom.Extent2D(-0.3103517169, -0.5363512808),
                    afwGeom.Extent2D(0.001092054612, 0.001887293861),
                    afwGeom.Extent2D(0.2248919247, 0.3886592703)]
        for shiftOld, shiftNew in zip(refShift, dcrShift):
            self.assertFloatsAlmostEqual(shiftOld.getX(), shiftNew.getX(), rtol=1e-6, atol=1e-8)
            self.assertFloatsAlmostEqual(shiftOld.getY(), shiftNew.getY(), rtol=1e-6, atol=1e-8)

    def testDcrSubfilterOrder(self):
        """Test that the bluest subfilter always has the largest amplitude.
        """
        dcrNumSubfilters = 3
        afwImage.utils.defineFilter("gTest", self.lambdaEff,
                                    lambdaMin=self.lambdaMin, lambdaMax=self.lambdaMax)
        filterInfo = afwImage.Filter("gTest")
        pixelScale = 0.2*arcseconds
        for testIter in range(self.nRandIter):
            rotAngle = 360.*self.rng.rand()*degrees
            azimuth = 360.*self.rng.rand()*degrees
            elevation = (45. + self.rng.rand()*40.)*degrees  # Restrict to 45 < elevation < 85 degrees
            visitInfo = self.makeDummyVisitInfo(azimuth, elevation)
            wcs = self.makeDummyWcs(rotAngle, pixelScale, crval=visitInfo.getBoresightRaDec())
            dcrShift = calculateDcr(visitInfo, wcs, filterInfo, dcrNumSubfilters)
            # First check that the blue subfilter amplitude is greater than the red subfilter
            rotation = calculateImageParallacticAngle(visitInfo, wcs).asRadians()
            ampShift = [dcr.getX()*np.sin(rotation) + dcr.getY()*np.cos(rotation) for dcr in dcrShift]
            self.assertGreater(ampShift[0], 0.)  # The blue subfilter should be shifted towards zenith
            self.assertLess(ampShift[2], 0.)  # The red subfilter should be shifted away from zenith
            # The absolute amplitude of the blue subfilter should also
            # be greater than that of the red subfilter
            self.assertGreater(np.abs(ampShift[0]), np.abs(ampShift[2]))

    def testApplyDcr(self):
        """Test that the image transformation reduces to a simple shift.
        """
        warpCtrl = afwMath.WarpingControl("lanczos3", "bilinear",
                                          cacheSize=0, interpLength=max(self.bbox.getDimensions()))
        dxVals = [-2, 1, 0, 1, 2]
        dyVals = [-2, 1, 0, 1, 2]
        x0 = 13
        y0 = 27
        # These offsets need further investigation: TODO DM-16119
        # It is not clear why the transformation must set pixels near any edge to "NO_DATA"
        maskOffsetStart = 2
        maskOffsetEnd = 3
        inputImage = afwImage.MaskedImageF(self.bbox)
        inputImage.image.array[y0, x0] = 1.
        maskValue = inputImage.mask.getPlaneBitMask("NO_DATA")
        for dx in dxVals:
            for dy in dyVals:
                shift = afwGeom.Extent2D(dx, dy)
                shiftedImage = applyDcr(inputImage, shift, warpCtrl, useInverse=False)
                # Create a blank reference image, and add the fake point source at the shifted location.
                refImage = afwImage.MaskedImageF(self.bbox)
                refImage.image.array[y0 + dy, x0 + dx] = 1.
                refImage.mask.array[:, 0:dx + maskOffsetStart] = maskValue
                refImage.mask.array[0:dy + maskOffsetStart, :] = maskValue
                if dx < maskOffsetEnd:
                    refImage.mask.array[:, dx - maskOffsetEnd:] = maskValue
                if dy < maskOffsetEnd:
                    refImage.mask.array[dy - maskOffsetEnd:, :] = maskValue
                self.assertMaskedImagesAlmostEqual(shiftedImage, refImage)

    def testRotationAngle(self):
        """Test that the sky rotation angle is consistently computed.

        The rotation is compared to pre-computed values.
        """
        cdRotAngle = 0.*degrees
        azimuth = 130.*degrees
        elevation = 70.*degrees
        pixelScale = 0.2*arcseconds
        visitInfo = self.makeDummyVisitInfo(azimuth, elevation)
        wcs = self.makeDummyWcs(cdRotAngle, pixelScale, crval=visitInfo.getBoresightRaDec())
        rotAngle = calculateImageParallacticAngle(visitInfo, wcs)
        refAngle = -0.9344289857053072*radians
        self.assertAnglesAlmostEqual(refAngle, rotAngle, maxDiff=1e-6*radians)

    def testRotationSouthZero(self):
        """Test that an observation pointed due South has zero rotation angle.

        An observation pointed South and on the meridian should have zenith
        directly to the North, and a parallactic angle of zero.
        """
        refAngle = 0.*degrees
        azimuth = 180.*degrees  # Telescope is pointed South
        pixelScale = 0.2*arcseconds
        for testIter in range(self.nRandIter):
            # Any additional arbitrary rotation should fall out of the calculation
            cdRotAngle = 360*self.rng.rand()*degrees
            elevation = (45. + self.rng.rand()*40.)*degrees  # Restrict to 45 < elevation < 85 degrees
            visitInfo = self.makeDummyVisitInfo(azimuth, elevation)
            wcs = self.makeDummyWcs(cdRotAngle, pixelScale, crval=visitInfo.getBoresightRaDec(), flipX=True)
            rotAngle = calculateImageParallacticAngle(visitInfo, wcs)
            self.assertAnglesAlmostEqual(refAngle - cdRotAngle, rotAngle, maxDiff=1e-6*radians)

    def testRotationFlipped(self):
        """Check the interpretation of rotations in the WCS.
        """
        doFlip = [False, True]
        for testIter in range(self.nRandIter):
            # Any additional arbitrary rotation should fall out of the calculation
            cdRotAngle = 360*self.rng.rand()*degrees
            # Make the telescope be pointed South, so that the parallactic angle is zero.
            azimuth = 180.*degrees
            elevation = (45. + self.rng.rand()*40.)*degrees  # Restrict to 45 < elevation < 85 degrees
            pixelScale = 0.2*arcseconds
            visitInfo = self.makeDummyVisitInfo(azimuth, elevation)
            for flip in doFlip:
                wcs = self.makeDummyWcs(cdRotAngle, pixelScale,
                                        crval=visitInfo.getBoresightRaDec(),
                                        flipX=flip)
                rotAngle = calculateImageParallacticAngle(visitInfo, wcs)
                if flip:
                    rotAngle *= -1
                self.assertAnglesAlmostEqual(cdRotAngle, rotAngle, maxDiff=1e-6*radians)

    def testConditionDcrModelNoChange(self):
        """Conditioning should not change the model if it equals the reference.

        This additionally tests that the variance and mask planes do not change.
        """
        dcrModels = DcrModel(modelImages=self.makeTestImages())
        newModels = [model.clone() for model in dcrModels]
        dcrModels.conditionDcrModel(newModels, self.bbox, gain=1.)
        for refModel, newModel in zip(dcrModels, newModels):
            self.assertMaskedImagesEqual(refModel, newModel)

    def testConditionDcrModelNoChangeHighGain(self):
        """Conditioning should not change the model if it equals the reference.

        This additionally tests that the variance and mask planes do not change.
        """
        dcrModels = DcrModel(modelImages=self.makeTestImages())
        newModels = [model.clone() for model in dcrModels]
        dcrModels.conditionDcrModel(newModels, self.bbox, gain=2.5)
        for refModel, newModel in zip(dcrModels, newModels):
            self.assertMaskedImagesAlmostEqual(refModel, newModel)

    def testConditionDcrModelWithChange(self):
        """Verify conditioning when the model changes by a known amount.

        This additionally tests that the variance and mask planes do not change.
        """
        dcrModels = DcrModel(modelImages=self.makeTestImages())
        newModels = [model.clone() for model in dcrModels]
        for model in newModels:
            model.image.array[:] *= 3.
        dcrModels.conditionDcrModel(newModels, self.bbox, gain=1.)
        for refModel, newModel in zip(dcrModels, newModels):
            refModel.image.array[:] *= 2.
            self.assertMaskedImagesAlmostEqual(refModel, newModel)

    def testRegularizationLargeClamp(self):
        """Frequency regularization should leave the models unchanged if the clamp factor is large.
        """
        clampFrequency = 3.
        regularizationWidth = 2
        dcrModels = DcrModel(modelImages=self.makeTestImages())
        newModels = [model.clone() for model in dcrModels]
        dcrModels.regularizeModelFreq(newModels, self.bbox, clampFrequency, regularizationWidth)
        for model, refModel in zip(newModels, dcrModels):
            self.assertMaskedImagesEqual(model, refModel)

    def testRegularizationSmallClamp(self):
        """Test that large variations between model planes are reduced.

        This also tests that noise-like pixels are not regularized.
        """
        clampFrequency = 1.1
        regularizationWidth = 2
        fluxRange = 10.
        dcrModels = DcrModel(modelImages=self.makeTestImages(fluxRange=fluxRange))
        newModels = [model.clone() for model in dcrModels]
        templateImage = dcrModels.getReferenceImage(self.bbox)

        dcrModels.regularizeModelFreq(newModels, self.bbox, clampFrequency, regularizationWidth)
        for model, refModel in zip(newModels, dcrModels):
            # The mask and variance planes should be unchanged
            self.assertFloatsEqual(model.mask.array, refModel.mask.array)
            self.assertFloatsEqual(model.variance.array, refModel.variance.array)
            # Make sure the test parameters do reduce the outliers
            self.assertGreater(np.max(refModel.image.array - templateImage),
                               np.max(model.image.array - templateImage))
            highThreshold = templateImage*clampFrequency
            highPix = model.image.array > highThreshold
            highPix = ndimage.morphology.binary_opening(highPix, iterations=regularizationWidth)
            self.assertFalse(np.all(highPix))
            lowThreshold = templateImage/clampFrequency
            lowPix = model.image.array < lowThreshold
            lowPix = ndimage.morphology.binary_opening(lowPix, iterations=regularizationWidth)
            self.assertFalse(np.all(lowPix))

    def testRegularizationSidelobes(self):
        """Test that artificial chromatic sidelobes are suppressed.
        """
        warpCtrl = afwMath.WarpingControl("lanczos3", "bilinear",
                                          cacheSize=0, interpLength=max(self.bbox.getDimensions()))
        clampFrequency = 2.
        regularizationWidth = 2
        noiseLevel = 0.1
        sourceAmplitude = 100.
        modelImages = self.makeTestImages(seed=5, nSrc=5, psfSize=3., noiseLevel=noiseLevel,
                                          detectionSigma=5., sourceSigma=sourceAmplitude, fluxRange=2.)
        templateImage = np.mean([model.image.array for model in modelImages], axis=0)
        sidelobeImages = self.makeTestImages(seed=5, nSrc=5, psfSize=1.5, noiseLevel=noiseLevel/10.,
                                             detectionSigma=5., sourceSigma=sourceAmplitude*5., fluxRange=2.)
        signList = [-1., 0., 1.]
        sidelobeShift = afwGeom.Extent2D(4., 0.)
        for model, sidelobe, sign in zip(modelImages, sidelobeImages, signList):
            sidelobe.image.array *= sign
            model += applyDcr(sidelobe, sidelobeShift, warpCtrl, useInverse=False)
            model += applyDcr(sidelobe, sidelobeShift, warpCtrl, useInverse=True)

        dcrModels = DcrModel(modelImages=modelImages)
        refModels = [dcrModels[subfilter].clone() for subfilter in range(self.dcrNumSubfilters)]

        dcrModels.regularizeModelFreq(modelImages, self.bbox, clampFrequency,
                                      regularizationWidth=regularizationWidth)
        for model, refModel, sign in zip(modelImages, refModels, signList):
            # The mask and variance planes should be unchanged
            self.assertFloatsEqual(model.mask.array, refModel.mask.array)
            self.assertFloatsEqual(model.variance.array, refModel.variance.array)
            if sign == 0:
                # The center subfilter does not have sidelobes, and should be unaffected.
                self.assertFloatsEqual(model.image.array, refModel.image.array)
            else:
                # Make sure the test parameters do reduce the outliers
                self.assertGreater(np.sum(np.abs(refModel.image.array - templateImage)),
                                   np.sum(np.abs(model.image.array - templateImage)))
            highThreshold = templateImage*clampFrequency
            highPix = model.image.array > highThreshold
            highPix = ndimage.morphology.binary_opening(highPix, iterations=regularizationWidth)
            self.assertFalse(np.all(highPix))
            lowThreshold = templateImage/clampFrequency
            lowPix = model.image.array < lowThreshold
            lowPix = ndimage.morphology.binary_opening(lowPix, iterations=regularizationWidth)
            self.assertFalse(np.all(lowPix))

    def testRegularizeModelIter(self):
        """Test that large amplitude changes between iterations are restricted.

        This also tests that noise-like pixels are not regularized.
        """
        modelClampFactor = 2.
        regularizationWidth = 2
        subfilter = 0
        dcrModels = DcrModel(modelImages=self.makeTestImages())
        oldModel = dcrModels[0]
        xSize, ySize = self.bbox.getDimensions()
        newModel = oldModel.clone()
        newModel.image.array[:] += self.rng.rand(ySize, xSize)*np.max(oldModel.image.array)
        newModelRef = newModel.clone()

        dcrModels.regularizeModelIter(subfilter, newModel, self.bbox, modelClampFactor, regularizationWidth)

        # The mask and variance planes should be unchanged
        self.assertFloatsEqual(newModel.mask.array, oldModel.mask.array)
        self.assertFloatsEqual(newModel.variance.array, oldModel.variance.array)
        # Make sure the test parameters do reduce the outliers
        self.assertGreater(np.max(newModelRef.image.array),
                           np.max(newModel.image.array - oldModel.image.array))
        # Check that all of the outliers are clipped
        highThreshold = oldModel.image.array*modelClampFactor
        highPix = newModel.image.array > highThreshold
        highPix = ndimage.morphology.binary_opening(highPix, iterations=regularizationWidth)
        self.assertFalse(np.all(highPix))
        lowThreshold = oldModel.image.array/modelClampFactor
        lowPix = newModel.image.array < lowThreshold
        lowPix = ndimage.morphology.binary_opening(lowPix, iterations=regularizationWidth)
        self.assertFalse(np.all(lowPix))

    def testIterateModel(self):
        """Test that the DcrModel is iterable, and has the right values.
        """
        testModels = self.makeTestImages()
        refVals = [np.sum(model.image.array) for model in testModels]
        dcrModels = DcrModel(modelImages=testModels)
        for refVal, model in zip(refVals, dcrModels):
            self.assertFloatsEqual(refVal, np.sum(model.image.array))
        # Negative indices are allowed, so check that those return models from the end.
        self.assertFloatsEqual(refVals[-1], np.sum(dcrModels[-1].image.array))


class MyMemoryTestCase(lsst.utils.tests.MemoryTestCase):
    pass


def setup_module(module):
    lsst.utils.tests.init()


if __name__ == "__main__":
    lsst.utils.tests.init()
    unittest.main()
