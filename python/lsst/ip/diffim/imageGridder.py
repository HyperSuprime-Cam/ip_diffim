from __future__ import absolute_import, division, print_function
from future import standard_library
standard_library.install_aliases()
#
# LSST Data Management System
# Copyright 2016 AURA/LSST.
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
#import scipy.fftpack

import lsst.afw.image as afwImage
import lsst.meas.algorithms as measAlg
import lsst.afw.math as afwMath
import lsst.afw.geom as afwGeom
import lsst.pex.config as pexConfig
import lsst.pipe.base as pipeBase

__all__ = ("ImageGridderTask", "ImageGridderConfig")


class ExampleImageGridSubtaskConfig(pexConfig.Config):
    """!
    \anchor ExampleImageGridSubtaskConfig_

    \brief Configuration parameters for the ExampleImageGridSubtask
    """
    addAmount = pexConfig.Field(
        dtype=float,
        doc="""Amount to add to image""",
        default=10.
    )

class ExampleImageGridSubtask(pipeBase.Task):
    ConfigClass = ExampleImageGridSubtaskConfig
    _defaultName = "ip_diffim_ExampleImageGridSubtask"

    def __init__(self, *args, **kwargs):
        """! Create the image gridding subTask
        @param *args arguments to be passed to lsst.pipe.base.task.Task.__init__
        @param **kwargs keyword arguments to be passed to lsst.pipe.base.task.Task.__init__
        """
        pipeBase.Task.__init__(self, *args, **kwargs)

    def run(self, subExp, expandedSubExp, fullBBox, **kwargs):
        """! Add `addAmount` to given subExposure.

        @param[in] subExp the sub-exposure of `exposure` upon which to operate
        @param[in] expandedSubExp the expanded sub-exposure of `exposure` upon which to operate
        @param[in] fullBBox the bounding box of the original exposure
        @return a `afw.Exp` or `afw.Exposure`
        """
        subExp = subExp.clone()
        img = subExp.getMaskedImage()
        img += self.config.addAmount
        return subExp


class ImageGridderConfig(pexConfig.Config):
    """!
    \anchor ImageGridderConfig_

    \brief Configuration parameters for the ImageGridderTask
    """

    gridSubtask = pexConfig.ConfigurableField(
        doc="Subtask to run on each subimage",
        target=ExampleImageGridSubtask,
    )

    gridSizeX = pexConfig.Field(
        dtype=float,
        doc="""Pixel dimensions of each grid cell in x direction""",
        default=10.
    )

    gridSizeY = pexConfig.Field(
        dtype=float,
        doc="""Pixel dimensions of each grid cell in y direction""",
        default=10.
    )

    gridStepX = pexConfig.Field(
        dtype=float,
        doc="""Spacing between subsequent grid cells in x direction. If equal to gridSizeX, then
               there is no overlap in the x direction.""",
        default=10.
    )

    gridStepY = pexConfig.Field(
        dtype=float,
        doc="""Spacing between subsequent grid cells in y direction. If equal to gridSizeY, then
               there is no overlap in the y direction.""",
        default=10.
    )

    borderSizeX = pexConfig.Field(
        dtype=float,
        doc="""Pixel dimensions of cell border in +/- x direction""",
        default=5.
    )

    borderSizeY = pexConfig.Field(
        dtype=float,
        doc="""Pixel dimensions of cell border in +/- y direction""",
        default=5.
    )

    rejiggerGridOption = pexConfig.Field(
        dtype=str,
        doc="""Adjust grid to fit in image by either modifying the 'spacing' (allowing overlaps),
                 or the 'size' of the grids""",
        default='spacing'
    )

    scaleByFwhm = pexConfig.Field(
        dtype=bool,
        doc="Scale gridSize/gridStep/borderSize/overlapSize by PSF FWHM?",
        default=True
    )

    reduceOperation = pexConfig.ChoiceField(
        dtype=str,
        doc="""Operation to use for combining subimages into new image.""",
        default="copy",
        allowed={
            "copy": "copy pixels directly from subimage (non-deterministic for overlaps)",
            "sum": "add pixels from overlaps (probably never wanted; used for testing)",
            "average": "average pixels from overlaps"
        }
    )

    ignoreMaskPlanes = pexConfig.ListField(
        dtype=str,
        doc="""Mask planes to ignore for sigma-clipped statistics""",
        default=("INTRP", "EDGE", "DETECTED", "SAT", "CR", "BAD", "NO_DATA", "DETECTED_NEGATIVE")
    )


## \addtogroup LSST_task_documentation
## \{
## \page ImageGridderTask
## \ref ImageGridderTask_ "ImageGridderTask"
##      Task for performing operations on an image over a specified grid
## \}


class ImageGridderTask(pipeBase.Task):
    """!
    \anchor ImageGridderTask_

    \brief Break an image task in to subimages on a grid and perform the same operation on each.

    \section ip_diffim_imageGridder_ImageGridderTask_Contents Contents

      - \ref ip_diffim_imageGridder_ImageGridderTask_Purpose
      - \ref ip_diffim_imageGridder_ImageGridderTask_Config
      - \ref ip_diffim_imageGridder_ImageGridderTask_Run
      - \ref ip_diffim_imageGridder_ImageGridderTask_Debug
      - \ref ip_diffim_imageGridder_ImageGridderTask_Example

    \section ip_diffim_imageGridder_ImageGridderTask_Purpose	Description

    Abstract super-task (run method not implemented) that enables a subclassed task
    to perform 'simple' operations on each subimage of a larger image, and then have
    those subimages stitched back together into a new, full-sized modified image.

    A subclass task will override the run method to perform operations on a passed image
    or exposure. This passed exposure will be pre-subimaged, but the function will also
    have access to the entire (original) image.

    \section ip_diffim_imageGridder_ImageGridderTask_Initialize       Task initialization

    \copydoc \_\_init\_\_

    \section ip_diffim_imageGridder_ImageGridderTask_Run       Invoking the Task

    \copydoc run

    \section ip_diffim_imageGridder_ImageGridderTask_Config       Configuration parameters

    See \ref ImageGridderConfig

    \section ip_diffim_imageGridder_ImageGridderTask_Debug		Debug variables

    This task has no debug variables

    \section ip_diffim_imageGridder_ImageGridderTask_Example	Example of using ImageGridderTask

    As it is a base class, this task has no standalone example, however its unit test
    \link tests/testImageGridder testImageGridder\endlink implements a basic subclass for testing.

    """
    ConfigClass = ImageGridderConfig
    _DefaultName = "ip_diffim_imageGridder"

    def __init__(self, *args, **kwargs):
        """! Create the image gridding Task
        @param *args arguments to be passed to lsst.pipe.base.task.Task.__init__
        @param **kwargs keyword arguments to be passed to lsst.pipe.base.task.Task.__init__
        """
        pipeBase.Task.__init__(self, *args, **kwargs)

        self.makeSubtask("gridSubtask")
        self.statsControl = afwMath.StatisticsControl()
        self.statsControl.setNumSigmaClip(3.)
        self.statsControl.setNumIter(3)
        self.statsControl.setAndMask(afwImage.MaskU.getPlaneBitMask(self.config.ignoreMaskPlanes))

    @pipeBase.timeMethod
    def run(self, exposure, returnPatches=False, **kwargs):
        """! Perform an operation on the given exposure.

        Break the exposure into sub-exps on a grid (parameters given by `ImageGridderConfig`)
        and perform `runSubtask` on each. Stitch together the resulting sub-exps generated by
        (or modified by) `runSubtask` into a final exposure of the same dimensions as the
        input `exposure`.

        @param[in] exposure the full exposure to process
        @return a `afw.Exposure`
        """
        self.log.info("Processing.")

        patches = self._makePatches(exposure, **kwargs)
        if returnPatches:
            return patches

        newMI = self._reduceImage(patches, exposure, **kwargs)
        return newMI

    def runSubtask(self, subExp, expandedSubExp, fullBBox, **kwargs):
        """! Run subtask to perform an operation on the given subExposure.

        Return an exposure of the same dimensions as `subExp`.
        Can use `expandedSubExp`, an expanded region of the original exposure,
        to perform computations. `subExp` and `expandedSubExp` should be considered
        *read-only* -- if you want to make changes to `subExp` it is recommended that
        you clone it first, and return the cloned, modified sub-exposure. This
        will be done in `gridSubtask.run()`.

        @param[in] subExp the sub-exposure of `exposure` upon which to operate
        @param[in] expandedSubExp the expanded sub-exposure of `exposure` upon which to operate
        @param[in] fullBBox the bounding box of the original exposure
        @return a `afw.Image` or `afw.Exposure`
        """
        subExp = self.gridSubtask.run(subExp, expandedSubExp, fullBBox, **kwargs)
        return subExp

    def _makePatches(self, exposure, **kwargs):
        """! Perform `runSubtask` on each patch

        Perform `runSubtask` on each patch across a grid on `exposure` generated by
        `generateGrid`.

        @param[in] exposure the original exposure which is used as the template
        @return a list of `afwExposure`s
        """
        boxes0, boxes1 = self._generateGrid(exposure)
        if len(boxes0) != len(boxes1):
            raise Exception('Uh oh!')   # TBD: define a specific exception to raise

        self.log.info("Processing %d sub-exposures" % len(boxes0))
        patches = []
        for i in range(len(boxes0)):
            #self.log.info("Processing on box: %s" % str(boxes0[i]))  # Wow! this is slow!
            subExp = afwImage.ExposureF(exposure, boxes0[i])  #.clone()
            expandedSubExp = afwImage.ExposureF(exposure, boxes1[i])  #.clone()
            result = self.runSubtask(subExp, expandedSubExp, exposure.getBBox(), **kwargs)
            patches.append(result)

        return patches

    def _reduceImage(self, patches, exposure, **kwargs):
        """! Reduce a set of sub-exposure patches into a final exposure

        Return an exposure of the same dimensions as `exposure`.
        `patches` is expected to have been produced by `makePatches`.

        @param[in] patches list of subExposures of `exposure` to merge
        @param[in] exposure the original exposure which is used as the template
        @return a `afw.Exposure`

        @notes Notes and currently known issues:
        1. This currently *should* correctly handle overlapping patches.
           For overlapping patches, use `config.reduceOperation='average'.
        2. This currently does not correctly handle varying PSFs (in fact,
           it just copies over the PSF from the original exposure)
        3. This logic currently makes *two* copies of the original exposure
           (one here and one in `_makePatches`). It is also slow.
        """
        newExp = afwImage.ExposureF(exposure).clone()
        newMI = newExp.getMaskedImage()
        newMI.getImage()[:, :] = 0.
        newMI.getVariance()[:, :] = 0.

        reduceOp = self.config.reduceOperation
        if reduceOp == 'average':  # make an array to keep track of weights
            weights = afwImage.ImageF(newMI.getBBox())  # Needs to be a float to divide later.

        for patch in patches:
            subExp = afwImage.ExposureF(newExp, patch.getBBox())
            subMI = subExp.getMaskedImage()
            patchMI = patch.getMaskedImage()
            if reduceOp == 'copy':
                subMI[:, :] = patchMI
            elif reduceOp == 'sum':
                subMI += patchMI
            elif reduceOp == 'average':
                subMI += patchMI
                wsubim = afwImage.ImageF(weights, patch.getBBox())
                wsubim += 1.

        if reduceOp == 'average':
            newMI /= weights
        return newExp

    def _generateGrid(self, exposure):
        """! Generate two lists of bounding boxes that evenly grid `exposure`

        Grid (subimage) centers will be spaced by gridStepX/Y. Then the grid will be adjusted
        as little as possible to evenly cover the input exposure (if rejiggerGridOption is True).
        Then the bounding boxes will be expanded by borderSizeX/Y. The expanded bounding
        boxes will be adjusted to ensure that they intersect the exposure's bounding box.
        The resulting lists of bounding boxes and corresponding expanded bounding boxes will
        be returned, and also set to `self.boxes0`, `self.boxes1`.

        @param[in] exposure an `afwImage.Exposure` whose full bounding box is to be evenly gridded.
        @return tuple containing two lists of `afwGeom.BoundingBox`es
        """
        # Extract the config parameters for conciseness.
        gridSizeX = self.config.gridSizeX
        gridSizeY = self.config.gridSizeY
        gridStepX = self.config.gridStepX
        gridStepY = self.config.gridStepY
        borderSizeX = self.config.borderSizeX
        borderSizeY = self.config.borderSizeY
        rejiggerGridOption = self.config.rejiggerGridOption
        scaleByFwhm = self.config.scaleByFwhm

        if scaleByFwhm:
            psfFwhm = exposure.getPsf().computeShape().getDeterminantRadius() * 2. * np.sqrt(2. * np.log(2.))

            def rescaleValue(val):
                return np.rint(val * psfFwhm).astype(int)

            gridSizeX = rescaleValue(gridSizeX)
            gridSizeY = rescaleValue(gridSizeY)
            gridStepX = rescaleValue(gridStepX)
            gridStepY = rescaleValue(gridStepY)
            borderSizeX = rescaleValue(borderSizeX)
            borderSizeY = rescaleValue(borderSizeY)

        bbox = exposure.getBBox()
        nGridX = bbox.getWidth() // gridStepX
        if rejiggerGridOption:
            nGridX = bbox.getWidth() / gridStepX
            # Readjust gridStepX so that it fits perfectly in the image.
            gridStepX = float(bbox.getWidth() - gridSizeX) / float(nGridX)

        nGridY = bbox.getWidth() // gridStepY
        if rejiggerGridOption:
            nGridY = bbox.getWidth() / gridStepY
            # Readjust gridStepY so that it fits perfectly in the image.
            gridStepY = float(bbox.getHeight() - gridSizeY) / float(nGridY)

        # first "main" box at 0,0
        bbox0 = afwGeom.Box2I(afwGeom.Point2I(bbox.getBegin()), afwGeom.Extent2I(gridSizeX, gridSizeY))
        # first expanded box
        bbox1 = afwGeom.Box2I(bbox0)
        bbox1.grow(afwGeom.Extent2I(borderSizeX, borderSizeY))

        # Offset the "main" (bbox0) and "expanded" (bbox1) bboxes by xoff, yoff. Clip them by the
        # exposure's bbox.
        def offsetAndClipBoxes(bbox0, bbox1, xoff, yoff, bbox):
            xoff = int(np.floor(xoff))
            yoff = int(np.floor(yoff))
            bb0 = afwGeom.Box2I(bbox0)
            bb0.shift(afwGeom.Extent2I(xoff, yoff))
            bb0.clip(bbox)
            bb1 = afwGeom.Box2I(bbox1)
            bb1.shift(afwGeom.Extent2I(xoff, yoff))
            bb1.clip(bbox)
            return bb0, bb1

        boxes0 = []
        boxes1 = []
        xoff = 0
        while(xoff <= bbox.getWidth()):
            yoff = 0
            while(yoff <= bbox.getHeight()):
                bb0, bb1 = offsetAndClipBoxes(bbox0, bbox1, xoff, yoff, bbox)
                boxes0.append(bb0)
                boxes1.append(bb1)
                yoff += gridStepY
            xoff += gridStepX

        return boxes0, boxes1

    def _plotBoxGrid(self, boxes, bbox, **kwargs):
        """! Plot a grid of boxes using matplotlib.

        @param[in] boxes a list of `afwGeom.BoundginBox`es
        @param[in] bbox an overall bounding box
        """
        import matplotlib.pyplot as plt

        def plotBox(box):
            corners = np.array([np.array([pt.getX(), pt.getY()]) for pt in box.getCorners()])
            corners = np.vstack([corners, corners[0, :]])
            plt.plot(corners[:, 0], corners[:, 1], **kwargs)

        for b in boxes:
            plotBox(b)
        plt.xlim(bbox.getBeginX(), bbox.getEndX())
        plt.ylim(bbox.getBeginY(), bbox.getEndY())

    def _plotBoxes(self, exposure):
        """! Plot both grids of boxes using matplotlib.

        `self.boxes0` and `self.boxes1` must have been set.
        @param[in] bbox an overall bounding box
        """
        import matplotlib.pyplot as plt

        bbox = exposure.getBBox()
        boxes0, boxes1 = self._generateGrid(exposure)
        self._plotBoxGrid(boxes0[::3], bbox, ls='--')
        # reset the color cycle -- see
        # http://stackoverflow.com/questions/24193174/reset-color-cycle-in-matplotlib
        plt.gca().set_prop_cycle(None)
        self._plotBoxGrid(boxes1[::3], bbox, ls=':')

    def _computeVarianceMean(self, subImage):
        """! Utility function: compute mean of variance plane of subimage

        @param[in] subImage the sub-image of `exposure` upon which to operate
        @return float clipped mean of masked variance plane of subImage
        """
        statObj = afwMath.makeStatistics(subImage.getMaskedImage().getVariance(),
                                         subImage.getMaskedImage().getMask(),
                                         afwMath.MEANCLIP, self.statsControl)
        var = statObj.getValue(afwMath.MEANCLIP)
        return var

    def _computePsf(self, subImage):
        """! Utility function: compute Psf at center of subImage.

        TBD: is this computing the Psf at the center of the subimage (i.e. center of its bounding box)?

        @param[in] subImage the sub-image of `exposure` upon which to operate
        @return 2d numpy.array of Psf for calculations.
        """
        return subImage.getPsf().computeImage().getArray()
