import numpy
import lsst.ip.diffim as ipDiffim
import lsst.detection as detection
import lsst.afw.math as afwMath
import lsst.afw.image as afwImage
import lsst.pex.exceptions as Exceptions
from   lsst.pex.logging import Trace
import lsst.ip.diffim.diffimDebug as ipDiffimDebug
import pdb

#######
# Helper functions used by all ip_diffim packages
#######

def fitFunction(function, values, errors, cols, rows, policy):
    # Fit a function to data
    nSigmaSq = policy.get('nSigmaSq')
    stepsize = policy.get('stepsize')

    # initialize fit parameters
    nPar = function.getNParameters()
    pars = numpy.zeros(nPar)       # start with no spatial variation
    pars[0]  = numpy.mean(values)  # except for the constant term
    stepsize = stepsize * numpy.ones(nPar)
    fit      = afwMath.minimize(function,
                                pars,
                                stepsize,
                                values,
                                errors,
                                cols,
                                rows,
                                nSigmaSq)
    if not fit.isValid:
        raise Exceptions.LsstRuntime('Spatial fit fails')

    return fit

def rejectKernelSumOutliers(spatialCells, policy):
    # Compare kernel sums; things that are bad (e.g. variable stars,
    # moving objects, cosmic rays) will have a kernel sum far from the
    # mean; reject these.
    
    maxOutlierIterations = policy.get('maxOutlierIterations')
    maxOutlierSigma      = policy.get('maxOutlierSigma')

    # So are we using pexLog.Trace or pexLog.Log?
    Trace('lsst.ip.diffim.rejectKernelSumOutliers', 4,
          'Rejecting kernels with deviant kSums');
    
    for nIter in xrange(maxOutlierIterations):
        kSumList = []
        idList   = []
        for scID, scPtr in enumerate(spatialCells):
            # Is the cell usable at all?
            if not scPtr.isUsable():
                continue
            # Is the contained model usable?
            if scPtr.getCurrentModel().getQaStatus():
                kSumList.append( scPtr.getCurrentModel().getKernelSum() )
                idList.append( scID )

        nCells = len(kSumList)

        if nCells == 0:
            raise Exceptions.LsstOutOfRange('No good cells found')

        kSumArray = numpy.array(kSumList)
        kSumMean  = kSumArray.mean()
        kSumStd   = kSumArray.std()

        # Reject kernels with aberrent statistics
        nRejected = 0
        for idx in range(nCells):
            if numpy.fabs( (kSumArray[idx]-kSumMean)/kSumStd ) > maxOutlierSigma:
                Trace('lsst.ip.diffim.rejectKernelSumOutliers', 5,
                      '# %s Kernel %d (kSum=%.3f) REJECTED due to bad kernel sum (mean=%.3f, std=%.3f)' %
                      (spatialCells[ idList[idx] ].getLabel(),
                       spatialCells[ idList[idx] ].getCurrentModel().getID(),
                       kSumArray[idx], kSumMean, kSumStd))
                
                # Set it as fully bad, since its original model is aberrant
                spatialCells[ idList[idx] ].getCurrentModel().setQaStatus(False)

                # Move to the next footprint in the cell
                spatialCells[ idList[idx] ].increment()
                nRejected += 1
                
        Trace('lsst.ip.diffim.rejectKernelSumOutliers', 4,
              'Kernel Sum Iteration %d, rejected %d kernels : Kernel Sum = %0.3f +/- %0.3f' %
              (nIter, nRejected, kSumMean, kSumStd))

        if nRejected == 0:
            break

    if nIter == (maxOutlierIterations-1) and nRejected != 0:
        Trace('lsst.ip.diffim.rejectKernelSumOutliers', 3,
              'Detection of kernels with deviant kSums reached its limit of %d iterations' %
              (maxOutlierIterations))

    Trace('lsst.ip.diffim.rejectKernelSumOutliers', 3,
          'Kernel Sum : %0.3f +/- %0.3f, %d kernels' % (kSumMean, kSumStd, nCells))


def createSpatialModelKernelCells(fpList,
                                  templateMaskedImage,
                                  scienceMaskedImage,
                                  kBasisList,
                                  policy,
                                  cFlag='c'):

    
    templateMaskedImagePtr = afwImage.MaskedImageFPtr(templateMaskedImage)
    scienceMaskedImagePtr  = afwImage.MaskedImageFPtr(scienceMaskedImage)
    
    nSegmentCol = policy.get('nSegmentCol')
    nSegmentRow = policy.get('nSegmentRow')

    nSegmentColPix = int( templateMaskedImage.getCols() / nSegmentCol )
    nSegmentRowPix = int( templateMaskedImage.getRows() / nSegmentRow )

    spatialCells   = ipDiffim.VectorSpatialModelCellF()
    
    cellCount = 0
    for col in range(nSegmentCol):
        colMin    = max(0, col*nSegmentColPix)
        colMax    = min(templateMaskedImage.getCols(), (col+1)*nSegmentColPix)
        colCenter = int( 0.5 * (colMin + colMax) )
        
        for row in range(nSegmentRow):
            rowMin    = max(0, row*nSegmentRowPix)
            rowMax    = min(templateMaskedImage.getRows(), (row+1)*nSegmentRowPix)
            rowCenter = int( 0.5 * (rowMin + rowMax) )

            label     = 'c%d' % cellCount

            fpPtrList = detection.FootprintContainerT()
            modelList = ipDiffim.VectorSpatialModelBaseF()

            # This is a bit blunt and could be more clever
            # Should never really have a loop within a loop within a loop
            # But we will not have *that many* Footprints...
            for fpID, fpPtr in enumerate(fpList):
                fpBBox = fpPtr.getBBox()
                fpMin  = fpBBox.min()
                fpMax  = fpBBox.max()
                fpColC = 0.5 * (fpMin.x() + fpMax.x())
                fpRowC = 0.5 * (fpMin.y() + fpMax.y())

                if (fpColC >= colMin) and (fpColC < colMax) and (fpRowC >= rowMin) and (fpRowC < rowMax):
                    fpPtrList.push_back(fpPtr)
                    
                    model = ipDiffim.SpatialModelKernelF(fpPtr,
                                                         templateMaskedImagePtr,
                                                         scienceMaskedImagePtr,
                                                         kBasisList,
                                                         policy,
                                                         False)

                    if policy.get('debugIO'):
                        ipDiffimDebug.writeDiffImages(cFlag, '%s_%d' % (label, fpID), model)
                        
                    modelList.push_back( model )
                    

            pdb.set_trace()
            spatialCell = ipDiffim.SpatialModelCellF(label, colCenter, rowCenter, fpPtrList, modelList)
            spatialCells.push_back(spatialCell)

            # Formatting to the screen 
            Trace('lsst.ip.diffim.createSpatialModelKernelCells', 2, '')

            cellCount += 1

    return spatialCells


