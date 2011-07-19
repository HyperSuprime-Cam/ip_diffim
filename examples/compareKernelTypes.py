#!/usr/bin/env python

# 
# LSST Data Management System
# Copyright 2008, 2009, 2010 LSST Corporation.
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

import os
import pdb
import sys
import unittest
import lsst.utils.tests as tests

import eups
import lsst.afw.geom as afwGeom
import lsst.afw.image as afwImage
import lsst.afw.math as afwMath
import lsst.ip.diffim as ipDiffim
import lsst.ip.diffim.diffimTools as diffimTools
import lsst.pex.logging as logging

import lsst.afw.display.ds9 as ds9

verbosity = 5
logging.Trace_setVerbosity('lsst.ip.diffim', verbosity)

display = True
writefits = False

# This one compares DeltaFunction and AlardLupton kernels
defSciencePath = None
defTemplatePath = None

class DiffimTestCases(unittest.TestCase):
    # D = I - (K.x.T + bg)
    def setUp(self):
        self.policy1     = ipDiffim.makeDefaultPolicy()
        self.policy2     = ipDiffim.makeDefaultPolicy()
        self.policy3     = ipDiffim.makeDefaultPolicy()

        self.policy1.set("kernelBasisSet", "delta-function")
        self.policy1.set("useRegularization", False)
        self.policy1.set("maxConditionNumber", 5.0e6)
        self.policy1.set("checkConditionNumber", False)
        self.policy1.set('fitForBackground', False)
        self.policy1.set('constantVarianceWeighting', True)
        self.kList1 = ipDiffim.makeKernelBasisList(self.policy1)
        self.bskv1  = ipDiffim.BuildSingleKernelVisitorF(self.kList1, self.policy1)
        
        self.policy2.set("kernelBasisSet", "delta-function")
        self.policy2.set("useRegularization", True)
        self.policy2.set("maxConditionNumber", 5.0e6)
        self.policy2.set("checkConditionNumber", False)
        self.policy2.set('fitForBackground', False)
        self.policy2.set('lambdaValue', 1000.0)
        self.policy2.set('constantVarianceWeighting', True)
        self.kList2 = ipDiffim.makeKernelBasisList(self.policy2)
        self.hMat2  = ipDiffim.makeRegularizationMatrix(self.policy2)
        self.bskv2  = ipDiffim.BuildSingleKernelVisitorF(self.kList2, self.policy2, self.hMat2)
        
        self.policy3.set("kernelBasisSet", "alard-lupton")
        self.policy3.set("maxConditionNumber", 5.0e7)
        self.policy3.set("checkConditionNumber", False)
        self.policy3.set('fitForBackground', False)
        self.policy3.set('constantVarianceWeighting', True)

        # lets look at deconvolution kernels
        #ipDiffim.modifyForDeconvolution(self.policy3)
        #print self.policy3
        #self.policy3.set("alardSigGauss", 0.75)
        #self.policy3.add("alardSigGauss", 1.0)
        #self.policy3.add("alardSigGauss", 1.25)
        #self.policy3.set("alardDegGauss", 6)
        #self.policy3.add("alardDegGauss", 4)
        #self.policy3.add("alardDegGauss", 2)
        
        self.kList3 = ipDiffim.makeKernelBasisList(self.policy3)
        self.bskv3  = ipDiffim.BuildSingleKernelVisitorF(self.kList3, self.policy3)

        defSciencePath = globals()['defSciencePath']
        defTemplatePath = globals()['defTemplatePath']
        if defSciencePath and defTemplatePath:
            self.scienceExposure   = afwImage.ExposureF(defSciencePath)
            self.templateExposure  = afwImage.ExposureF(defTemplatePath)
        else:
            defDataDir = eups.productDir('afwdata')
            defSciencePath = os.path.join(defDataDir, "DC3a-Sim", "sci", "v26-e0",
                                          "v26-e0-c011-a00.sci")
            defTemplatePath = os.path.join(defDataDir, "DC3a-Sim", "sci", "v5-e0",
                                           "v5-e0-c011-a00.sci")
            
            self.scienceExposure   = afwImage.ExposureF(defSciencePath)
            self.templateExposure  = afwImage.ExposureF(defTemplatePath)
            warper = afwMath.Warper.fromPolicy(self.policy1.getPolicy("warpingPolicy"))
            self.templateExposure = warper.warpExposure(self.scienceExposure.getWcs(), self.templateExposure,
                destBBox = self.scienceExposure.getBBox(afwImage.PARENT))


        # image statistics
        self.dStats  = ipDiffim.ImageStatisticsF()

        #
        tmi = self.templateExposure.getMaskedImage()
        smi = self.scienceExposure.getMaskedImage()

        detPolicy = self.policy1.getPolicy("detectionPolicy")
        detPolicy.set("detThreshold", 50.)
        detPolicy.set("detOnTemplate", False)
        kcDetect = ipDiffim.KernelCandidateDetectionF(detPolicy)
        kcDetect.apply(tmi, smi)
        self.footprints = kcDetect.getFootprints()

        
    def tearDown(self):
        del self.policy1
        del self.policy2
        del self.policy3
        del self.kList1
        del self.kList2
        del self.kList3
        del self.hMat2
        del self.bskv1
        del self.bskv2
        del self.bskv3
        del self.scienceExposure
        del self.templateExposure

    def apply(self, policy, visitor, xloc, yloc, tmi, smi):
        kc     = ipDiffim.makeKernelCandidate(xloc, yloc, tmi, smi, policy)
        visitor.processCandidate(kc)
        kim    = kc.getKernelImage(ipDiffim.KernelCandidateF.RECENT)
        diffIm = kc.getDifferenceImage(ipDiffim.KernelCandidateF.RECENT)
        kSum   = kc.getKsum(ipDiffim.KernelCandidateF.RECENT)
        bg     = kc.getBackground(ipDiffim.KernelCandidateF.RECENT)

        bbox = kc.getKernel(ipDiffim.KernelCandidateF.RECENT).shrinkBBox(diffIm.getBBox(afwImage.LOCAL))
        diffIm = afwImage.MaskedImageF(diffIm, bbox, afwImage.LOCAL)
        self.dStats.apply(diffIm)
        
        dmean = afwMath.makeStatistics(diffIm.getImage(),    afwMath.MEAN).getValue()
        dstd  = afwMath.makeStatistics(diffIm.getImage(),    afwMath.STDEV).getValue()
        vmean = afwMath.makeStatistics(diffIm.getVariance(), afwMath.MEAN).getValue()
        return kSum, bg, dmean, dstd, vmean, kim, diffIm, kc
        
    def applyVisitor(self, invert=False, xloc=397, yloc=580):
        print '# %.2f %.2f' % (xloc, yloc)

        imsize = int(3 * self.policy1.get("kernelSize"))

        # chop out a region around a known object
        bbox = afwGeom.Box2I(afwGeom.Point2I(xloc - imsize/2,
                                             yloc - imsize/2),
                             afwGeom.Point2I(xloc + imsize/2,
                                             yloc + imsize/2) )

        # sometimes the box goes off the image; no big deal...
        try:
            if invert:
                tmi  = afwImage.MaskedImageF(self.scienceExposure.getMaskedImage(), bbox, afwImage.LOCAL)
                smi  = afwImage.MaskedImageF(self.templateExposure.getMaskedImage(), bbox, afwImage.LOCAL)
            else:
                smi  = afwImage.MaskedImageF(self.scienceExposure.getMaskedImage(), bbox, afwImage.LOCAL)
                tmi  = afwImage.MaskedImageF(self.templateExposure.getMaskedImage(), bbox, afwImage.LOCAL)
        except Exception, e:
            return None

        # delta function kernel
        results1 = self.apply(self.policy1, self.bskv1, xloc, yloc, tmi, smi)
        kSum1, bg1, dmean1, dstd1, vmean1, kImageOut1, diffIm1, kc1 = results1
        kc1.getKernelSolution(ipDiffim.KernelCandidateF.RECENT).getConditionNumber(
            ipDiffim.KernelSolution.EIGENVALUE)
        kc1.getKernelSolution(ipDiffim.KernelCandidateF.RECENT).getConditionNumber(
            ipDiffim.KernelSolution.SVD)
        print 'DF Diffim residuals : %.2f +/- %.2f; %.2f, %.2f; %.2f %.2f, %.2f' % (self.dStats.getMean(),
                                                                                    self.dStats.getRms(),
                                                                                    kSum1, bg1,
                                                                                    dmean1, dstd1, vmean1)
        if display:
            ds9.mtv(tmi, frame=1) # ds9 switches frame 0 and 1 for some reason
            ds9.mtv(smi, frame=0)
            ds9.mtv(kImageOut1, frame=2)
            ds9.mtv(diffIm1, frame=3)
        if writefits:
            tmi.writeFits('t')
            smi.writeFits('s')
            kImageOut1.writeFits('k1.fits')
            diffIm1.writeFits('d1')

        # regularized delta function kernel
        results2 = self.apply(self.policy2, self.bskv2, xloc, yloc, tmi, smi)
        kSum2, bg2, dmean2, dstd2, vmean2, kImageOut2, diffIm2, kc2 = results2
        kc2.getKernelSolution(ipDiffim.KernelCandidateF.RECENT).getConditionNumber(
            ipDiffim.KernelSolution.EIGENVALUE)
        kc2.getKernelSolution(ipDiffim.KernelCandidateF.RECENT).getConditionNumber(
            ipDiffim.KernelSolution.SVD)
        print 'DFr Diffim residuals : %.2f +/- %.2f; %.2f, %.2f; %.2f %.2f, %.2f' % (self.dStats.getMean(),
                                                                                     self.dStats.getRms(),
                                                                                     kSum2, bg2,
                                                                                     dmean2, dstd2, vmean2)
        if display:
            ds9.mtv(tmi, frame=4)
            ds9.mtv(smi, frame=5)
            ds9.mtv(kImageOut2, frame=6)
            ds9.mtv(diffIm2, frame=7)
        if writefits:
            kImageOut2.writeFits('k2.fits')
            diffIm2.writeFits('d2')

        # alard-lupton kernel
        results3 = self.apply(self.policy3, self.bskv3, xloc, yloc, tmi, smi)
        kSum3, bg3, dmean3, dstd3, vmean3, kImageOut3, diffIm3, kc3 = results3
        kc3.getKernelSolution(ipDiffim.KernelCandidateF.RECENT).getConditionNumber(
            ipDiffim.KernelSolution.EIGENVALUE)
        kc3.getKernelSolution(ipDiffim.KernelCandidateF.RECENT).getConditionNumber(
            ipDiffim.KernelSolution.SVD)
        print 'AL Diffim residuals : %.2f +/- %.2f; %.2f, %.2f; %.2f %.2f, %.2f' % (self.dStats.getMean(),
                                                                                    self.dStats.getRms(),
                                                                                    kSum3, bg3,
                                                                                    dmean3, dstd3, vmean3)
        # outputs
        if display:
            ds9.mtv(tmi, frame=8)
            ds9.mtv(smi, frame=9)
            ds9.mtv(kImageOut3, frame=10)
            ds9.mtv(diffIm3, frame=11)
        if writefits:
            kImageOut3.writeFits('k3.fits')
            diffIm3.writeFits('d3')

        raw_input('Next: ')

    def testFunctor(self):
        for fp in self.footprints:
            # note this returns the kernel images
            self.applyVisitor(invert=False, 
                              xloc= int(0.5 * ( fp.getBBox().getMinX() + fp.getBBox().getMaxX() )),
                              yloc= int(0.5 * ( fp.getBBox().getMinY() + fp.getBBox().getMaxY() )))
       
#####
        
def suite():
    """Returns a suite containing all the test cases in this module."""
    tests.init()

    suites = []
    suites += unittest.makeSuite(DiffimTestCases)
    suites += unittest.makeSuite(tests.MemoryTestCase)
    return unittest.TestSuite(suites)

def run(doExit=False):
    """Run the tests"""
    tests.run(suite(), doExit)

if __name__ == "__main__":
    from optparse import OptionParser
    parser = OptionParser()
    parser.add_option('-n', dest='nodisplay', action='store_true', default=False)
    parser.add_option('-w', dest='writefits', action='store_true', default=False)
    parser.add_option('-t', dest='defTemplatePath')
    parser.add_option('-i', dest='defSciencePath')
    (opt, args) = parser.parse_args()

    display = not opt.nodisplay
    writefits = opt.writefits
    if opt.defTemplatePath and opt.defSciencePath:
        defTemplatePath = opt.defTemplatePath
        defSciencePath = opt.defSciencePath
        
    run(True)
