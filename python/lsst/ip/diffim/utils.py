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
# see <http://www.lsstcorp.org/LegalNotices/>.
#

"""Support utilities for Measuring sources"""
import numpy as np
import lsst.pex.logging as pexLog
import lsst.afw.detection as afwDet
import lsst.afw.geom as afwGeom
import lsst.afw.image as afwImage
import lsst.afw.math as afwMath
import lsst.afw.table as afwTable
import lsst.afw.display.ds9 as ds9
import lsst.afw.display.utils as displayUtils
import lsst.meas.algorithms as measAlg

from . import diffimLib
from . import diffimTools
from . import dipoleFitTask

# Export DipoleTestImage to expose fake image generating funcs
__all__ = ("DipoleTestImage")


keptPlots = False                       # Have we arranged to keep spatial plots open?

def showSourceSet(sSet, xy0=(0, 0), frame=0, ctype=ds9.GREEN, symb="+", size=2):
    """Draw the (XAstrom, YAstrom) positions of a set of Sources.  Image has the given XY0"""

    with ds9.Buffering():
        for s in sSet:
            xc, yc = s.getXAstrom() - xy0[0], s.getYAstrom() - xy0[1]

            if symb == "id":
                ds9.dot(str(s.getId()), xc, yc, frame=frame, ctype=ctype, size=size)
            else:
                ds9.dot(symb, xc, yc, frame=frame, ctype=ctype, size=size)

#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
#
# Kernel display utilities
#
def showKernelSpatialCells(maskedIm, kernelCellSet, showChi2=False, symb="o",
                           ctype=None, ctypeUnused=None, ctypeBad=None, size=3,
                           frame=None, title="Spatial Cells"):
    """Show the SpatialCells.  If symb is something that ds9.dot
    understands (e.g. "o"), the top nMaxPerCell candidates will be
    indicated with that symbol, using ctype and size"""

    ds9.mtv(maskedIm, frame=frame, title=title)
    with ds9.Buffering():
        origin = [-maskedIm.getX0(), -maskedIm.getY0()]
        for cell in kernelCellSet.getCellList():
            displayUtils.drawBBox(cell.getBBox(), origin=origin, frame=frame)

            goodies = ctypeBad is None
            for cand in cell.begin(goodies):
                cand = diffimLib.cast_KernelCandidateF(cand)
                xc, yc = cand.getXCenter() + origin[0], cand.getYCenter() + origin[1]
                if cand.getStatus() == afwMath.SpatialCellCandidate.BAD:
                    color = ctypeBad
                elif cand.getStatus() == afwMath.SpatialCellCandidate.GOOD:
                    color = ctype
                elif cand.getStatus() == afwMath.SpatialCellCandidate.UNKNOWN:
                    color = ctypeUnused
                else:
                    continue

                if color:
                    ds9.dot(symb, xc, yc, frame=frame, ctype=color, size=size)

                    if showChi2:
                        rchi2 = cand.getChi2()
                        if rchi2 > 1e100:
                            rchi2 = np.nan
                        ds9.dot("%d %.1f" % (cand.getId(), rchi2),
                                xc - size, yc - size - 4, frame=frame, ctype=color, size=size)


def showDiaSources(sources, exposure, isFlagged, isDipole, frame=None):
    """Display Dia Sources
    """
    #
    # Show us the ccandidates
    #
    # Too many mask planes in diffims
    for plane in ("BAD", "CR", "EDGE", "INTERPOlATED", "INTRP", "SAT", "SATURATED"):
        ds9.setMaskPlaneVisibility(plane, False)

    mos = displayUtils.Mosaic()
    for i in range(len(sources)):
        source = sources[i]
        badFlag = isFlagged[i]
        dipoleFlag = isDipole[i]
        bbox = source.getFootprint().getBBox()
        stamp = exposure.Factory(exposure, bbox, True)
        im = displayUtils.Mosaic(gutter=1, background=0, mode="x")
        im.append(stamp.getMaskedImage())
        lab = "%.1f,%.1f:" % (source.getX(), source.getY())
        if badFlag:
            ctype = ds9.RED
            lab += "BAD"
        if dipoleFlag:
            ctype = ds9.YELLOW
            lab += "DIPOLE"
        if not badFlag and not dipoleFlag:
            ctype = ds9.GREEN
            lab += "OK"
        mos.append(im.makeMosaic(), lab, ctype)
        #print source.getId()
    title = "Dia Sources"
    mosaicImage = mos.makeMosaic(frame=frame, title=title)
    return mosaicImage

def showKernelCandidates(kernelCellSet, kernel, background, frame=None, showBadCandidates=True,
                         resids=False, kernels=False):
    """Display the Kernel candidates.
    If kernel is provided include spatial model and residuals;  
    If chi is True, generate a plot of residuals/sqrt(variance), i.e. chi
    """

    #
    # Show us the ccandidates
    #
    if kernels:
        mos = displayUtils.Mosaic(gutter=5, background=0)
    else:
        mos = displayUtils.Mosaic(gutter=5, background=-1)
    #
    candidateCenters = []
    candidateCentersBad = []
    candidateIndex = 0
    for cell in kernelCellSet.getCellList():
        for cand in cell.begin(False): # include bad candidates
            cand = diffimLib.cast_KernelCandidateF(cand)

            # Original difference image; if does not exist, skip candidate
            try:
                resid = cand.getDifferenceImage(diffimLib.KernelCandidateF.ORIG)
            except Exception:
                continue

            rchi2 = cand.getChi2()
            if rchi2 > 1e100:
                rchi2 = np.nan

            if not showBadCandidates and cand.isBad():
                continue

            im_resid = displayUtils.Mosaic(gutter=1, background=-0.5, mode="x")

            try:
                im = cand.getScienceMaskedImage()
                im = im.Factory(im, True)
                im.setXY0(cand.getScienceMaskedImage().getXY0())
            except Exception:
                continue
            if (not resids and not kernels):
                im_resid.append(im.Factory(im, True))
            try:
                im = cand.getTemplateMaskedImage()
                im = im.Factory(im, True)
                im.setXY0(cand.getTemplateMaskedImage().getXY0())
            except Exception:
                continue
            if (not resids and not kernels):
                im_resid.append(im.Factory(im, True))

            # Difference image with original basis
            if resids:
                var = resid.getVariance()
                var = var.Factory(var, True)
                np.sqrt(var.getArray(), var.getArray()) # inplace sqrt
                resid = resid.getImage()
                resid /= var
                bbox = kernel.shrinkBBox(resid.getBBox())
                resid = resid.Factory(resid, bbox, True)
            elif kernels:
                kim = cand.getKernelImage(diffimLib.KernelCandidateF.ORIG).convertF()
                resid = kim.Factory(kim, True)
            im_resid.append(resid)

            # residuals using spatial model
            ski  = afwImage.ImageD(kernel.getDimensions())
            kernel.computeImage(ski, False, int(cand.getXCenter()), int(cand.getYCenter()))
            sk   = afwMath.FixedKernel(ski)
            sbg  = 0.0
            if background:
                sbg = background(int(cand.getXCenter()), int(cand.getYCenter()))
            sresid = cand.getDifferenceImage(sk, sbg)
            resid  = sresid
            if resids:
                resid = sresid.getImage()
                resid /= var
                bbox = kernel.shrinkBBox(resid.getBBox())
                resid = resid.Factory(resid, bbox, True)
            elif kernels:
                kim = ski.convertF()
                resid = kim.Factory(kim, True)
            im_resid.append(resid)

            im = im_resid.makeMosaic()

            lab = "%d chi^2 %.1f" % (cand.getId(), rchi2)
            ctype = ds9.RED if cand.isBad() else ds9.GREEN

            mos.append(im, lab, ctype)

            if False and np.isnan(rchi2):
                ds9.mtv(cand.getScienceMaskedImage.getImage(), title="candidate", frame=1)
                print "rating",  cand.getCandidateRating()

            im = cand.getScienceMaskedImage()
            center = (candidateIndex, cand.getXCenter() - im.getX0(), cand.getYCenter() - im.getY0())
            candidateIndex += 1
            if cand.isBad():
                candidateCentersBad.append(center)
            else:
                candidateCenters.append(center)

    if resids:
        title = "chi Diffim"
    elif kernels:
        title = "Kernels"
    else:
        title = "Candidates & residuals"
    mosaicImage = mos.makeMosaic(frame=frame, title=title)

    return mosaicImage

def showKernelBasis(kernel, frame=None):
    """Display a Kernel's basis images
    """
    mos = displayUtils.Mosaic()

    for k in kernel.getKernelList():
        im = afwImage.ImageD(k.getDimensions())
        k.computeImage(im, False)
        mos.append(im)
    mos.makeMosaic(frame=frame, title="Kernel Basis Images")

    return mos

###############


def importMatplotlib():
    """!Import matplotlib.pyplot when needed, warn if not available.
    @return the imported module if available, else False.

    """
    try:
        import matplotlib.pyplot as plt
        return plt
    except ImportError as err:
        log = pexLog.Log(pexLog.getDefaultLog(),
                         'lsst.ip.diffim.utils', pexLog.INFO)
        log.warn('Unable to import matplotlib: %s' % err)
        return False


def plotKernelSpatialModel(kernel, kernelCellSet, showBadCandidates=True, 
                           numSample=128, keepPlots=True, maxCoeff = 10):
    """Plot the Kernel spatial model."""

    plt = importMatplotlib()
    if not plt:
        return
    import matplotlib.colors

    x0 = kernelCellSet.getBBox().getBeginX()
    y0 = kernelCellSet.getBBox().getBeginY()

    candPos = list()
    candFits = list()
    badPos = list()
    badFits = list()
    candAmps = list()
    badAmps = list()
    for cell in kernelCellSet.getCellList():
        for cand in cell.begin(False):
            cand = diffimLib.cast_KernelCandidateF(cand)
            if not showBadCandidates and cand.isBad():
                continue
            candCenter = afwGeom.PointD(cand.getXCenter(), cand.getYCenter())
            try:
                im = cand.getTemplateMaskedImage()
            except Exception, e:
                continue

            targetFits = badFits if cand.isBad() else candFits
            targetPos = badPos if cand.isBad() else candPos
            targetAmps = badAmps if cand.isBad() else candAmps

            # compare original and spatial kernel coefficients
            kp0 = np.array(cand.getKernel(diffimLib.KernelCandidateF.ORIG).getKernelParameters())
            amp = cand.getCandidateRating()

            targetFits = badFits if cand.isBad() else candFits
            targetPos = badPos if cand.isBad() else candPos
            targetAmps = badAmps if cand.isBad() else candAmps

            targetFits.append(kp0)
            targetPos.append(candCenter)
            targetAmps.append(amp)

    xGood = np.array([pos.getX() for pos in candPos]) - x0
    yGood = np.array([pos.getY() for pos in candPos]) - y0
    zGood = np.array(candFits)

    xBad = np.array([pos.getX() for pos in badPos]) - x0
    yBad = np.array([pos.getY() for pos in badPos]) - y0
    zBad = np.array(badFits)
    numBad = len(badPos)

    xRange = np.linspace(0, kernelCellSet.getBBox().getWidth(), num=numSample)
    yRange = np.linspace(0, kernelCellSet.getBBox().getHeight(), num=numSample)

    if maxCoeff:
        maxCoeff = min(maxCoeff, kernel.getNKernelParameters())
    else:
        maxCoeff = kernel.getNKernelParameters()

    for k in range(maxCoeff):
        func = kernel.getSpatialFunction(k)
        dfGood = zGood[:,k] - np.array([func(pos.getX(), pos.getY()) for pos in candPos])
        yMin = dfGood.min()
        yMax = dfGood.max()
        if numBad > 0:
            dfBad = zBad[:,k] - np.array([func(pos.getX(), pos.getY()) for pos in badPos])
            # Can really screw up the range...
            yMin = min([yMin, dfBad.min()])
            yMax = max([yMax, dfBad.max()])
        yMin -= 0.05 * (yMax - yMin)
        yMax += 0.05 * (yMax - yMin)

        fRange = np.ndarray((len(xRange), len(yRange)))
        for j, yVal in enumerate(yRange):
            for i, xVal in enumerate(xRange):
                fRange[j][i] = func(xVal, yVal)

        fig = plt.figure(k)

        fig.clf()
        try:
            fig.canvas._tkcanvas._root().lift() # == Tk's raise, but raise is a python reserved word
        except Exception:                                 # protect against API changes
            pass

        fig.suptitle('Kernel component %d' % k)

        # LL
        ax = fig.add_axes((0.1, 0.05, 0.35, 0.35))
        vmin = fRange.min() # - 0.05 * np.fabs(fRange.min())
        vmax = fRange.max() # + 0.05 * np.fabs(fRange.max())
        norm = matplotlib.colors.Normalize(vmin=vmin, vmax=vmax)
        im = ax.imshow(fRange, aspect='auto', norm=norm,
                       extent=[0, kernelCellSet.getBBox().getWidth()-1,
                               0, kernelCellSet.getBBox().getHeight()-1])
        ax.set_title('Spatial polynomial')
        plt.colorbar(im, orientation='horizontal', ticks=[vmin, vmax])

        # UL
        ax = fig.add_axes((0.1, 0.55, 0.35, 0.35))
        ax.plot(-2.5*np.log10(candAmps), zGood[:,k], 'b+')
        if numBad > 0:
            ax.plot(-2.5*np.log10(badAmps), zBad[:,k], 'r+')
        ax.set_title("Basis Coefficients")
        ax.set_xlabel("Instr mag")
        ax.set_ylabel("Coeff")

        # LR
        ax = fig.add_axes((0.55, 0.05, 0.35, 0.35))
        ax.set_autoscale_on(False)
        ax.set_xbound(lower=0, upper=kernelCellSet.getBBox().getHeight())
        ax.set_ybound(lower=yMin, upper=yMax)
        ax.plot(yGood, dfGood, 'b+')
        if numBad > 0:
            ax.plot(yBad, dfBad, 'r+')
        ax.axhline(0.0)
        ax.set_title('dCoeff (indiv-spatial) vs. y')

        # UR
        ax = fig.add_axes((0.55, 0.55, 0.35, 0.35))
        ax.set_autoscale_on(False)
        ax.set_xbound(lower=0, upper=kernelCellSet.getBBox().getWidth())
        ax.set_ybound(lower=yMin, upper=yMax)
        ax.plot(xGood, dfGood, 'b+')
        if numBad > 0:
            ax.plot(xBad, dfBad, 'r+')
        ax.axhline(0.0)
        ax.set_title('dCoeff (indiv-spatial) vs. x')

        fig.show()

    global keptPlots
    if keepPlots and not keptPlots:
        # Keep plots open when done
        def show():
            print "%s: Please close plots when done." % __name__
            try:
                plt.show()
            except Exception:
                pass
            print "Plots closed, exiting..."
        import atexit
        atexit.register(show)
        keptPlots = True


def showKernelMosaic(bbox, kernel, nx=7, ny=None, frame=None, title=None, 
                     showCenter=True, showEllipticity=True):
    """Show a mosaic of Kernel images.
    """
    mos = displayUtils.Mosaic()

    x0 = bbox.getBeginX()
    y0 = bbox.getBeginY()
    width = bbox.getWidth()
    height = bbox.getHeight()

    if not ny:
        ny = int(nx*float(height)/width + 0.5)
        if not ny:
            ny = 1

    schema = afwTable.SourceTable.makeMinimalSchema()
    control = measAlg.GaussianCentroidControl()
    centroider = measAlg.MeasureSourcesBuilder().addAlgorithm(control).build(schema)
    sdssShape = measAlg.SdssShapeControl()
    shaper = measAlg.MeasureSourcesBuilder().addAlgorithm(sdssShape).build(schema)
    table = afwTable.SourceTable.make(schema)
    table.defineCentroid(control.name)
    table.defineShape(sdssShape.name)

    centers = []
    shapes = []
    for iy in range(ny):
        for ix in range(nx):
            x = int(ix*(width-1)/(nx-1)) + x0
            y = int(iy*(height-1)/(ny-1)) + y0

            im = afwImage.ImageD(kernel.getDimensions())
            ksum = kernel.computeImage(im, False, x, y)
            lab = "Kernel(%d,%d)=%.2f" % (x, y, ksum) if False else ""
            mos.append(im, lab)

            exp = afwImage.makeExposure(afwImage.makeMaskedImage(im))
            w, h = im.getWidth(), im.getHeight()
            cen = afwGeom.PointD(w//2, h//2)
            src = table.makeRecord()
            foot = afwDet.Footprint(exp.getBBox())
            src.setFootprint(foot)

            centroider.apply(src, exp, cen)
            centers.append((src.getX(), src.getY()))

            shaper.apply(src, exp, cen)
            shapes.append((src.getIxx(), src.getIxy(), src.getIyy()))

    mos.makeMosaic(frame=frame, title=title if title else "Model Kernel", mode=nx)

    if centers and frame is not None:
        i = 0
        with ds9.Buffering():
            for cen, shape in zip(centers, shapes):
                bbox = mos.getBBox(i); i += 1
                xc, yc = cen[0] + bbox.getMinX(),  cen[1] + bbox.getMinY()
                if showCenter:
                    ds9.dot("+", xc, yc,  ctype=ds9.BLUE, frame=frame)

                if showEllipticity:
                    ixx, ixy, iyy = shape
                    ds9.dot("@:%g,%g,%g" % (ixx, ixy, iyy), xc, yc, frame=frame, ctype=ds9.RED)

    return mos

def plotPixelResiduals(exposure, warpedTemplateExposure, diffExposure, kernelCellSet,
                       kernel, background, testSources, config,
                       origVariance = False, nptsFull = 1e6, keepPlots = True, titleFs=14):
    """Plot diffim residuals for LOCAL and SPATIAL models"""
    candidateResids = []
    spatialResids   = []
    nonfitResids    = []

    for cell in kernelCellSet.getCellList():
        for cand in cell.begin(True): # only look at good ones
            # Be sure
            if not (cand.getStatus() == afwMath.SpatialCellCandidate.GOOD):
                continue

            cand    = diffimLib.cast_KernelCandidateF(cand)
            diffim  = cand.getDifferenceImage(diffimLib.KernelCandidateF.ORIG)
            orig    = cand.getScienceMaskedImage()

            ski     = afwImage.ImageD(kernel.getDimensions())
            kernel.computeImage(ski, False, int(cand.getXCenter()), int(cand.getYCenter()))
            sk      = afwMath.FixedKernel(ski)
            sbg     = background(int(cand.getXCenter()), int(cand.getYCenter()))
            sdiffim = cand.getDifferenceImage(sk, sbg)

            # trim edgs due to convolution
            bbox    = kernel.shrinkBBox(diffim.getBBox())
            tdiffim  = diffim.Factory(diffim, bbox)
            torig    = orig.Factory(orig, bbox)
            tsdiffim = sdiffim.Factory(sdiffim, bbox)

            if origVariance:
                candidateResids.append(np.ravel(tdiffim.getImage().getArray() /
                                                np.sqrt(torig.getVariance().getArray())))
                spatialResids.append(np.ravel(tsdiffim.getImage().getArray() /
                                              np.sqrt(torig.getVariance().getArray())))
            else:
                candidateResids.append(np.ravel(tdiffim.getImage().getArray() /
                                                np.sqrt(tdiffim.getVariance().getArray())))
                spatialResids.append(np.ravel(tsdiffim.getImage().getArray() /
                                              np.sqrt(tsdiffim.getVariance().getArray())))

    fullIm   = diffExposure.getMaskedImage().getImage().getArray()
    fullMask = diffExposure.getMaskedImage().getMask().getArray()
    if origVariance:
        fullVar  = exposure.getMaskedImage().getVariance().getArray()
    else:
        fullVar  = diffExposure.getMaskedImage().getVariance().getArray()

    bitmaskBad  = 0
    bitmaskBad |= afwImage.MaskU.getPlaneBitMask('NO_DATA')
    bitmaskBad |= afwImage.MaskU.getPlaneBitMask('SAT')
    idx = np.where((fullMask & bitmaskBad) == 0)
    stride = int(len(idx[0]) // nptsFull)
    sidx = idx[0][::stride], idx[1][::stride]
    allResids = fullIm[sidx] / np.sqrt(fullVar[sidx])

    testFootprints = diffimTools.sourceToFootprintList(testSources, warpedTemplateExposure, 
                                                       exposure, config, pexLog.getDefaultLog())
    for fp in testFootprints:
        subexp = diffExposure.Factory(diffExposure, fp["footprint"].getBBox())
        subim  = subexp.getMaskedImage().getImage()
        if origVariance:
            subvar = afwImage.ExposureF(exposure, fp["footprint"].getBBox()).getMaskedImage().getVariance()
        else:
            subvar = subexp.getMaskedImage().getVariance()
        nonfitResids.append(np.ravel(subim.getArray() / np.sqrt(subvar.getArray())))

    candidateResids = np.ravel(np.array(candidateResids))
    spatialResids   = np.ravel(np.array(spatialResids))
    nonfitResids    = np.ravel(np.array(nonfitResids))

    plt = importMatplotlib()
    if not plt:
        return

    from matplotlib.font_manager import FontProperties

    fig = plt.figure()
    fig.clf()
    try:
        fig.canvas._tkcanvas._root().lift() # == Tk's raise, but raise is a python reserved word
    except Exception:                                 # protect against API changes
        pass
    if origVariance:
        fig.suptitle("Diffim residuals: Normalized by sqrt(input variance)", fontsize=titleFs)
    else:
        fig.suptitle("Diffim residuals: Normalized by sqrt(diffim variance)", fontsize=titleFs)

    sp1 = plt.subplot(221)
    sp2 = plt.subplot(222, sharex=sp1, sharey=sp1)
    sp3 = plt.subplot(223, sharex=sp1, sharey=sp1)
    sp4 = plt.subplot(224, sharex=sp1, sharey=sp1)
    xs  = np.arange(-5, 5.05, 0.1)
    ys  = 1. / np.sqrt(2 * np.pi) * np.exp( -0.5 * xs**2 )

    sp1.hist(candidateResids, bins=xs, normed=True, alpha=0.5, label="N(%.2f, %.2f)"
             % (np.mean(candidateResids), np.var(candidateResids)))
    sp1.plot(xs, ys, "r-", lw=2, label="N(0,1)")
    sp1.set_title("Candidates: basis fit", fontsize=titleFs-2)
    sp1.legend(loc=1, fancybox=True, shadow=True, prop = FontProperties(size=titleFs-6))

    sp2.hist(spatialResids, bins=xs, normed=True, alpha=0.5, label="N(%.2f, %.2f)"
             % (np.mean(spatialResids), np.var(spatialResids)))
    sp2.plot(xs, ys, "r-", lw=2, label="N(0,1)")
    sp2.set_title("Candidates: spatial fit", fontsize=titleFs-2)
    sp2.legend(loc=1, fancybox=True, shadow=True, prop = FontProperties(size=titleFs-6))

    sp3.hist(nonfitResids, bins=xs, normed=True, alpha=0.5, label="N(%.2f, %.2f)"
             % (np.mean(nonfitResids), np.var(nonfitResids)))
    sp3.plot(xs, ys, "r-", lw=2, label="N(0,1)")
    sp3.set_title("Control sample: spatial fit", fontsize=titleFs-2)
    sp3.legend(loc=1, fancybox=True, shadow=True, prop = FontProperties(size=titleFs-6))

    sp4.hist(allResids, bins=xs, normed=True, alpha=0.5, label="N(%.2f, %.2f)"
             % (np.mean(allResids), np.var(allResids)))
    sp4.plot(xs, ys, "r-", lw=2, label="N(0,1)")
    sp4.set_title("Full image (subsampled)", fontsize=titleFs-2)
    sp4.legend(loc=1, fancybox=True, shadow=True, prop = FontProperties(size=titleFs-6))

    plt.setp(sp1.get_xticklabels()+sp1.get_yticklabels(), fontsize=titleFs-4)
    plt.setp(sp2.get_xticklabels()+sp2.get_yticklabels(), fontsize=titleFs-4)
    plt.setp(sp3.get_xticklabels()+sp3.get_yticklabels(), fontsize=titleFs-4)
    plt.setp(sp4.get_xticklabels()+sp4.get_yticklabels(), fontsize=titleFs-4)

    sp1.set_xlim(-5, 5)
    sp1.set_ylim(0, 0.5)
    fig.show()

    global keptPlots
    if keepPlots and not keptPlots:
        # Keep plots open when done
        def show():
            print "%s: Please close plots when done." % __name__
            try:
                plt.show()
            except Exception:
                pass
            print "Plots closed, exiting..."
        import atexit
        atexit.register(show)
        keptPlots = True

def calcCentroid(arr):
    """Calculate first moment of a (kernel) image"""
    y, x = arr.shape
    sarr = arr*arr
    xarr = np.asarray([[el for el in range(x)] for el2 in range(y)])
    yarr = np.asarray([[el2 for el in range(x)] for el2 in range(y)])
    narr = xarr*sarr
    sarrSum = sarr.sum()
    centx = narr.sum()/sarrSum
    narr = yarr*sarr
    centy = narr.sum()/sarrSum
    return centx, centy

def calcWidth(arr, centx, centy):
    """Calculate second moment of a (kernel) image"""
    y, x = arr.shape
    #Square the flux so we don't have to deal with negatives
    sarr = arr*arr
    xarr = np.asarray([[el for el in range(x)] for el2 in range(y)])
    yarr = np.asarray([[el2 for el in range(x)] for el2 in range(y)])
    narr = sarr*np.power((xarr - centx), 2.)
    sarrSum = sarr.sum()
    xstd = np.sqrt(narr.sum()/sarrSum)
    narr = sarr*np.power((yarr - centy), 2.)
    ystd = np.sqrt(narr.sum()/sarrSum)
    return xstd, ystd

def printSkyDiffs(sources, wcs):
    """Print differences in sky coordinates between source Position and its Centroid mapped through Wcs"""
    for s in sources:
        sCentroid = s.getCentroid()
        sPosition = s.getCoord().getPosition()
        dra = 3600*(sPosition.getX() - wcs.pixelToSky(sCentroid.getX(),
                                                      sCentroid.getY()).getPosition().getX())/0.2
        ddec = 3600*(sPosition.getY() - wcs.pixelToSky(sCentroid.getX(),
                                                       sCentroid.getY()).getPosition().getY())/0.2
        if np.isfinite(dra) and np.isfinite(ddec):
            print dra, ddec

def makeRegions(sources, outfilename, wcs=None):
    """Create regions file for ds9 from input source list"""
    fh = open(outfilename, "w")
    fh.write("global color=red font=\"helvetica 10 normal\" select=1 highlite=1 edit=1 move=1 delete=1 include=1 fixed=0 source\nfk5\n")
    for s in sources:
        if wcs:
            (ra, dec) = wcs.pixelToSky(s.getCentroid().getX(), s.getCentroid().getY()).getPosition()
        else:
            (ra, dec) = s.getCoord().getPosition()
        if np.isfinite(ra) and np.isfinite(dec):
            fh.write("circle(%f,%f,2\")\n"%(ra,dec))
    fh.flush()
    fh.close()

def showSourceSetSky(sSet, wcs, xy0, frame=0, ctype=ds9.GREEN, symb="+", size=2):
    """Draw the (RA, Dec) positions of a set of Sources. Image has the XY0."""
    with ds9.Buffering():
        for s in sSet:
            (xc, yc) = wcs.skyToPixel(s.getCoord().getRa(), s.getCoord().getDec())
            xc -= xy0[0]
            yc -= xy0[1]
            ds9.dot(symb, xc, yc, frame=frame, ctype=ctype, size=size)

def plotWhisker(results, newWcs):
    """Plot whisker diagram of astromeric offsets between results.matches"""
    refCoordKey = results.matches[0].first.getTable().getCoordKey()
    inCentroidKey = results.matches[0].second.getTable().getCentroidKey()
    positions = [m.first.get(refCoordKey) for m in results.matches]
    residuals = [m.first.get(refCoordKey).getOffsetFrom(
                       newWcs.pixelToSky(m.second.get(inCentroidKey))) for
                       m in results.matches]
    plt = importMatplotlib()
    if not plt:
        return
    fig = plt.figure()
    sp = fig.add_subplot(1, 1, 0)
    xpos = [x[0].asDegrees() for x in positions]
    ypos = [x[1].asDegrees() for x in positions]
    xpos.append(0.02*(max(xpos) - min(xpos)) + min(xpos))
    ypos.append(0.98*(max(ypos) - min(ypos)) + min(ypos))
    xidxs = np.isfinite(xpos)
    yidxs = np.isfinite(ypos)
    X = np.asarray(xpos)[xidxs]
    Y = np.asarray(ypos)[yidxs]
    distance = [x[1].asArcseconds() for x in residuals]
    distance.append(0.2)
    distance = np.asarray(distance)[xidxs]
    #NOTE: This assumes that the bearing is measured positive from +RA through North.
    #From the documentation this is not clear.
    bearing = [x[0].asRadians() for x in residuals]
    bearing.append(0)
    bearing = np.asarray(bearing)[xidxs]
    U = (distance*np.cos(bearing))
    V = (distance*np.sin(bearing))
    sp.quiver(X, Y, U, V)
    sp.set_title("WCS Residual")
    plt.show()


class DipoleTestImage(object):
    """Utility class for dipole measurement testing

    Generate an image with simulated dipoles and noise; store the original "pre-subtraction" images
    and catalogs as well.
    Used to generate test data for DMTN-007.
    """

    def __init__(self, w=101, h=101, xcenPos=[27.], ycenPos=[25.], xcenNeg=[23.], ycenNeg=[25.],
                 psfSigma=2., flux=[30000.], fluxNeg=None, noise=10., gradientParams=None):
        self.w = w
        self.h = h
        self.xcenPos = xcenPos
        self.ycenPos = ycenPos
        self.xcenNeg = xcenNeg
        self.ycenNeg = ycenNeg
        self.psfSigma = psfSigma
        self.flux = flux
        self.fluxNeg = fluxNeg
        if fluxNeg is None:
            self.fluxNeg = self.flux
        self.noise = noise
        self.gradientParams = gradientParams
        self._makeDipoleImage()

    def _makeDipoleImage(self):
        """Generate an exposure and catalog with the given dipole source(s)"""

        posImage, posCatalog = self._makeStarImage(
            xc=self.xcenPos, yc=self.ycenPos, flux=self.flux)

        negImage, negCatalog = self._makeStarImage(
            xc=self.xcenNeg, yc=self.ycenNeg, flux=self.fluxNeg)

        dipole = posImage.clone()
        di = dipole.getMaskedImage()
        di -= negImage.getMaskedImage()

        # Carry through pos/neg detection masks to new planes in diffim
        dm = di.getMask()
        posDetectedBits = posImage.getMaskedImage().getMask().getArray() == dm.getPlaneBitMask("DETECTED")
        negDetectedBits = negImage.getMaskedImage().getMask().getArray() == dm.getPlaneBitMask("DETECTED")
        pos_det = dm.addMaskPlane("DETECTED_POS")  # new mask plane -- different from "DETECTED"
        neg_det = dm.addMaskPlane("DETECTED_NEG")  # new mask plane -- different from "DETECTED_NEGATIVE"
        dma = dm.getArray()
        # set the two custom mask planes to these new masks
        dma[:, :] = posDetectedBits*pos_det + negDetectedBits*neg_det
        self.diffim, self.posImage, self.posCatalog, self.negImage, self.negCatalog \
            = dipole, posImage, posCatalog, negImage, negCatalog

    def _makeStarImage(self, xc=[15.3], yc=[18.6], flux=[2500], schema=None):
        """Generate an exposure and catalog with the given stellar source(s)"""

        from lsst.meas.base.tests import TestDataset
        bbox = afwGeom.Box2I(afwGeom.Point2I(0, 0), afwGeom.Point2I(self.w-1, self.h-1))
        dataset = TestDataset(bbox, psfSigma=self.psfSigma, threshold=1.)

        for i in xrange(len(xc)):
            dataset.addSource(flux=flux[i], centroid=afwGeom.Point2D(xc[i], yc[i]))

        if schema is None:
            schema = TestDataset.makeMinimalSchema()
        exposure, catalog = dataset.realize(noise=self.noise, schema=schema)

        if self.gradientParams is not None:
            y, x = np.mgrid[:self.w, :self.h]
            gp = self.gradientParams
            gradient = gp[0] + gp[1] * x + gp[2] * y
            if len(self.gradientParams) > 3:  # it includes a set of 2nd-order polynomial params
                gradient += gp[3] * x*y + gp[4] * x*x + gp[5] * y*y
            imgArr = exposure.getMaskedImage().getArrays()[0]
            imgArr += gradient

        return exposure, catalog

    def fitDipoleSource(self, source, **kwds):
        alg = dipoleFitTask.DipoleFitAlgorithm(self.diffim, self.posImage, self.negImage)
        fitResult = alg.fitDipole(source, **kwds)
        return fitResult

    def displayImages(self):
        displayExposure(self.diffim)
        displayExposure(self.posImage)
        displayExposure(self.negImage)

    def displayCutouts(self, source, asHeavyFootprint=True):
        displayCutouts(source, self.diffim, self.posImage, self.negImage, asHeavyFootprint)

    def detectDipoleSources(self, doMerge=True, diffim=None, detectSigma=5.5, grow=3):
        """Utility function for detecting dipoles.

        Detect pos/neg sources in the diffim, then merge them. A
        bigger "grow" parameter leads to a larger footprint which
        helps with dipole measurement for faint dipoles.

        """

        if diffim is None:
            diffim = self.diffim

        # Start with a minimal schema - only the fields all SourceCatalogs need
        schema = afwTable.SourceTable.makeMinimalSchema()

        # Customize the detection task a bit (optional)
        detectConfig = measAlg.SourceDetectionConfig()
        detectConfig.returnOriginalFootprints = False  # should be the default

        psfSigma = diffim.getPsf().computeShape().getDeterminantRadius()

        # code from imageDifference.py:
        detectConfig.thresholdPolarity = "both"
        detectConfig.thresholdValue = detectSigma
        # detectConfig.nSigmaToGrow = psfSigma
        detectConfig.reEstimateBackground = True  # if False, will fail often for faint sources on gradients?
        detectConfig.thresholdType = "pixel_stdev"

        # Create the detection task. We pass the schema so the task can declare a few flag fields
        detectTask = measAlg.SourceDetectionTask(schema, config=detectConfig)

        table = afwTable.SourceTable.make(schema)
        catalog = detectTask.makeSourceCatalog(table, diffim, sigma=psfSigma)

        # Now do the merge.
        if doMerge:
            fpSet = catalog.fpSets.positive
            fpSet.merge(catalog.fpSets.negative, grow, grow, False)
            sources = afwTable.SourceCatalog(table)
            fpSet.makeSources(sources)

            return sources

        else:
            return detectTask, schema


# ######## UTILITIES FUNCTIONS FOR PLOTTING  ####

# Utility class containing methods for displaying dipoles/footprints
# in difference images, mostly used for debugging.


def display2dArray(arr, title='Data', showBars=True, extent=None):
    """Use matplotlib.pyplot.imshow() to display a 2-D array.

    @param arr The 2-D array to display
    @param title Optional title to display
    @param showBars Show grey-scale bar alongside
    @param extent If not None, a 4-tuple giving the bounding box coordinates of the array

    @return matplotlib.pyplot.figure dispaying the image
    """
    plt = importMatplotlib()
    if not plt:
        return

    fig = plt.imshow(arr, origin='lower', interpolation='none', cmap='gray',
                     extent=extent)
    plt.title(title)
    if showBars:
        plt.colorbar(fig, cmap='gray')
    return fig


def displayImage(image, showBars=True, width=8, height=2.5):
    """Use matplotlib.pyplot.imshow() to display an afw.image.Image within
    its bounding box.

    @see displayImages()
    """
    return displayImages((image), showBars=True, width=8, height=2.5)


def displayImages(images, showBars=True, width=8, height=2.5):
    """Use matplotlib.pyplot.imshow() to display up to three
    afw.image.Images alongside each other, each within its
    bounding box.

    @see display2dArray() for params not listed here.
    @param images tuple of up to three images to display
    @param image The image to display
    @param width The width of the display (inches)
    @param height The height of the display (inches)

    @return matplotlib.pyplot.figure dispaying the image

    """
    plt = importMatplotlib()
    if not plt:
        return

    fig = plt.figure(figsize=(width, height))
    for i, image in enumerate(images):
        bbox = image.getBBox()
        extent = (bbox.getBeginX(), bbox.getEndX(), bbox.getBeginY(), bbox.getEndY())
        plt.subplot(1, len(images), i+1)
        ma = image.getArray()
        display2dArray(ma, title='Data', showBars=showBars, extent=extent)
    return fig


def displayMaskedImage(maskedImage, showMasks=True, showVariance=False, showBars=True, width=8,
                       height=2.5):
    """Use matplotlib.pyplot.imshow() to display a afwImage.MaskedImageF,
    alongside its masks and variance plane

    @see displayImage() for params not listed here

    @param maskedImage MaskedImage to display
    @param showMasks Display the MaskedImage's masks
    @param showVariance Display the MaskedImage's variance plane

    @return matplotlib.pyplot.figure dispaying the image

    """
    plt = importMatplotlib()
    if not plt:
        return

    fig = plt.figure(figsize=(width, height))
    bbox = maskedImage.getBBox()
    extent = (bbox.getBeginX(), bbox.getEndX(), bbox.getBeginY(), bbox.getEndY())
    plt.subplot(1, 3, 1)
    ma = maskedImage.getArrays()
    display2dArray(ma[0], title='Data', showBars=showBars, extent=extent)
    if showMasks:
        plt.subplot(1, 3, 2)
        display2dArray(ma[1], title='Masks', showBars=showBars, extent=extent)
    if showVariance:
        plt.subplot(1, 3, 3)
        display2dArray(ma[2], title='Variance', showBars=showBars, extent=extent)
    return fig


def displayExposure(exposure, showMasks=True, showVariance=False, showPsf=False, showBars=True,
                    width=8, height=2.5):
    """Use matplotlib.pyplot.imshow() to display a afw.image.Exposure,
    including its masks and variance plane and optionally its Psf.

    @see displayMaskedImage() for params not listed here

    @param exposure Exposure to display
    @param showPsf Display the exposure's Psf

    @return matplotlib.pyplot.figure dispaying the image

    """
    plt = importMatplotlib()
    if not plt:
        return

    fig = displayMaskedImage(exposure.getMaskedImage(), showMasks,
                             showVariance=not showPsf,
                             showBars=showBars, width=width, height=height)
    if showPsf:
        plt.subplot(1, 3, 3)
        psfIm = exposure.getPsf().computeImage()
        bbox = psfIm.getBBox()
        extent = (bbox.getBeginX(), bbox.getEndX(), bbox.getBeginY(), bbox.getEndY())
        display2dArray(psfIm.getArray(), title='PSF', showBars=showBars, extent=extent)
    return fig


def displayCutouts(source, exposure, posImage=None, negImage=None, asHeavyFootprint=False, title=''):
    """Use matplotlib.pyplot.imshow() to display cutouts within up to
    three afw.image.Exposure's, given by an input SourceRecord.

    @param source afw.table.SourceRecord defining the footprint to extract and display
    @param exposure afw.image.Exposure from which to extract the cutout to display
    @param posImage Second exposure from which to extract the cutout to display
    @param negImage Third exposure from which to extract the cutout to display
    @param asHeavyFootprint Display the cutouts as
    afw.detection.HeavyFootprint, with regions outside the
    footprint removed

    @return matplotlib.pyplot.figure dispaying the image

    """
    plt = importMatplotlib()
    if not plt:
        return

    fp = source.getFootprint()
    bbox = fp.getBBox()
    extent = (bbox.getBeginX(), bbox.getEndX(), bbox.getBeginY(), bbox.getEndY())

    fig = plt.figure(figsize=(8, 2.5))
    if not asHeavyFootprint:
        subexp = afwImage.ImageF(exposure.getMaskedImage().getImage(), bbox, afwImage.PARENT)
    else:
        hfp = afwDet.HeavyFootprintF(fp, exposure.getMaskedImage())
        subexp = getHeavyFootprintSubimage(hfp)
    plt.subplot(1, 3, 1)
    display2dArray(subexp.getArray(), title=title+' Diffim', extent=extent)
    if posImage is not None:
        if not asHeavyFootprint:
            subexp = afwImage.ImageF(posImage.getMaskedImage().getImage(), bbox, afwImage.PARENT)
        else:
            hfp = afwDet.HeavyFootprintF(fp, posImage.getMaskedImage())
            subexp = getHeavyFootprintSubimage(hfp)
        plt.subplot(1, 3, 2)
        display2dArray(subexp.getArray(), title=title+' Pos', extent=extent)
    if negImage is not None:
        if not asHeavyFootprint:
            subexp = afwImage.ImageF(negImage.getMaskedImage().getImage(), bbox, afwImage.PARENT)
        else:
            hfp = afwDet.HeavyFootprintF(fp, negImage.getMaskedImage())
            subexp = getHeavyFootprintSubimage(hfp)
        plt.subplot(1, 3, 3)
        display2dArray(subexp.getArray(), title=title+' Neg', extent=extent)
    return fig


def makeHeavyCatalog(catalog, exposure, verbose=False):
    """Turn all footprints in a catalog into heavy footprints."""
    for i, source in enumerate(catalog):
        fp = source.getFootprint()
        if not fp.isHeavy():
            if verbose:
                print(i, 'not heavy => heavy')
            hfp = afwDet.HeavyFootprintF(fp, exposure.getMaskedImage())
            source.setFootprint(hfp)

    return catalog


def getHeavyFootprintSubimage(fp, badfill=np.nan, grow=0):
    """Extract the image from a heavyFootprint as an ImageF."""
    hfp = afwDet.HeavyFootprintF_cast(fp)
    bbox = hfp.getBBox()
    if grow > 0:
        bbox.grow(grow)

    subim2 = afwImage.ImageF(bbox, badfill)  # set the mask to NA (can use 0. if desired)
    afwDet.expandArray(hfp, hfp.getImageArray(), subim2.getArray(), bbox.getCorners()[0])
    return subim2


def searchCatalog(catalog, x, y):
    """Search a catalog for a source whose footprint contains the given x, y pixel coordinates."""
    for i, s in enumerate(catalog):
        bbox = s.getFootprint().getBBox()
        if bbox.contains(afwGeom.Point2D(x, y)):
            print(i)
            return s

