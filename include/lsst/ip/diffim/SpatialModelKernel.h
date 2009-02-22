// -*- lsst-c++ -*-
/**
 * @file
 *
 * @brief Class derived from SpatialModelBase for spatial Kernel fitting
 *
 * @author Andrew Becker, University of Washington
 *
 * @ingroup afw
 */

#ifndef LSST_IP_DIFFIM_SPATIALMODELKERNEL_H
#define LSST_IP_DIFFIM_SPATIALMODELKERNEL_H

#include <boost/shared_ptr.hpp>

#include <lsst/afw/math/Kernel.h>
#include <lsst/afw/math/KernelFunctions.h>
#include <lsst/pex/policy/Policy.h>
#include <lsst/afw/detection/Footprint.h>
#include <lsst/sdqa/SdqaRating.h>

#include <lsst/ip/diffim/SpatialModelBase.h>
#include <lsst/ip/diffim/ImageSubtract.h>

namespace lsst {
namespace ip {
namespace diffim {

    /** 
     * 
     * @brief Class derived from SpatialModelBase for spatial Kernel fitting
     * 
     * Derived class of SpatialModelBase.  A Kernel model is built for a given
     * Footprint within a MaskedImage.  An ensemble of Kernels, distributed
     * evenly across the image using SpatialModelCell, is used to fit for a
     * spatial function.  If this Kernel is a poor fit to the spatial function,
     * another member of SpatialModelCell will be used instead.
     *
     * This class needs to know how to build itself, meaning it requires the
     * basis functions used to create the Kernel, as well as the input images
     * that it is to compare.
     *
     * @see lsst/ip/diffim/SpatialModelBase.h for base class
     */    
    template <typename ImageT>
    class SpatialModelKernel : public SpatialModelBase<ImageT> {
    public: 
        typedef boost::shared_ptr<SpatialModelKernel<ImageT> > Ptr;
        typedef std::vector<Ptr> SpatialModelKernelPtrList;
        typedef boost::shared_ptr<lsst::afw::image::MaskedImage<ImageT> > MaskedImagePtr; 

        /** Empty constructor
         */
        //SpatialModelKernel();

        /** Constructor
         *
         * @note Kernel needs to carry around pointer to the parent image
         * 
         * @param fpPtr  Pointer to footprint of pixels used to build Kernel
         * @param miToConvolveParentPtr  Pointer to parent template image
         * @param miToNotConvolveParentPtr  Pointer to parent science image
         * @param kernelFunctor  Functor to build the PSF Mathching Kernel
         * @param policy  Policy for operations
         * @param build  Build upon construction?  Default is false.
         */
        SpatialModelKernel(lsst::afw::detection::Footprint::Ptr const& fpPtr,
                           MaskedImagePtr const& miToConvolvePtr,
                           MaskedImagePtr const& miToNotConvolvePtr,
                           boost::shared_ptr<PsfMatchingFunctor<ImageT> > const& kernelFunctor,
                           lsst::pex::policy::Policy const& policy,
                           bool build=false);

        /** Destructor
         */
        virtual ~SpatialModelKernel() {};

        /** Execute the time-consuming process of building the local model
         * 
         * Overrides virtual function of base class
         */
        bool buildModel();

        /** Return Sdqa rating
         * 
         * Overrides virtual function of base class
         */
        double returnSdqaRating(lsst::pex::policy::Policy &policy);

        /** Get Footprint pointer for the Kernel model
         */
        lsst::afw::detection::Footprint::Ptr const& getFootprintPtr() const {return _fpPtr;};

        /** Get template's MaskedImage pointer for the Kernel model
         */
        MaskedImagePtr const& getMiToConvolvePtr() const {return _miToConvolvePtr;};

        /** Get image's MaskedImage pointer for the Kernel model
         */
        MaskedImagePtr const& getMiToNotConvolvePtr() const {return _miToNotConvolvePtr;};


        /** Set Kernel pointer associated with the Footprint; the core of this Model
         *
         * @param kPtr  pointer to the Kernel
         */
        void setKernelPtr(boost::shared_ptr<lsst::afw::math::Kernel> kPtr) {_kPtr = kPtr;};
        /** Get Kernel pointer associated with the Footprint
         */
        boost::shared_ptr<lsst::afw::math::Kernel> const& getKernelPtr() const {return _kPtr;};

        /** Set pointer associated with the uncertainty in the Kernel
         *
         * @param kPtr  pointer to the Kernel uncertainty; represent as a Kernel
         */
        void setKernelErrPtr(boost::shared_ptr<lsst::afw::math::Kernel> kPtr) {_kErrPtr = kPtr;};
        /** Get pointer associated with the uncertainty in the Kernel
         */
        boost::shared_ptr<lsst::afw::math::Kernel> getKernelErrPtr() {return _kErrPtr;};

        /** Set Kernel sum
         *
         * @param kSum  Kernel sum
         */
        void setKernelSum(double kSum) {_kSum = kSum;};
        /** Get Kernel sum
         */
        double getKernelSum() {return _kSum;};

        /** Set differential background value associated with the Kernel
         *
         * @param bg  Background value
         */
        void setBg(double bg) {_bg = bg;};
        /** Get differential background value associated with the Kernel
         */
        double getBg() {return _bg;};

        /** Set uncertainty in the differential background determination
         *
         * @param bgErr  Uncertainty in background 
         */
        void setBgErr(double bgErr) {_bgErr = bgErr;};
        /** Get uncertainty in the differential background determination
         */
        double getBgErr() {return _bgErr;};

        /** Set differential background value associated with the Kernel
         *
         * @param bg  Background value
         */
        void setBackground(double bg) {_bg = bg;};
        /** Get differential background value associated with the Kernel
         */
        double getBackground() {return _bg;};

        /** Set uncertainty in the differential background determination
         *
         * @param bgErr  Uncertainty in background 
         */
        void setBackgroundErr(double bgErr) {_bgErr = bgErr;};
        /** Get uncertainty in the differential background determination
         */
        double getBackgroundErr() {return _bgErr;};

        /** Set class instance associated with residuals in the derived difference image
         *
         * @param kStats  Pointer to instance of FootprintFunctor ImageStatistics class
         *
         * @note Ideally will be replaced by Sdqa
         *
         * @note Has to be a pointer since there is no empty constructor of FootprintFunctor
         */
        void setStats(boost::shared_ptr<ImageStatistics<lsst::afw::image::MaskedImage<ImageT> > > kStats) {_kStats = kStats;};
        /** Get class instance associated with residuals in the derived difference image
         */
        boost::shared_ptr<ImageStatistics<lsst::afw::image::MaskedImage<ImageT> > > getStats() {return _kStats;};

    private: 
        /** Objects needed to build itself; only initializable during construction
         */
        lsst::afw::detection::Footprint::Ptr const& _fpPtr; ///< Footprint containing pixels used to build Kernel
        MaskedImagePtr const& _miToConvolvePtr;             ///< Subimage around which you build kernel
        MaskedImagePtr const& _miToNotConvolvePtr;          ///< Subimage around which you build kernel
        boost::shared_ptr<PsfMatchingFunctor<ImageT> > const& _kFunctor; ///< Functor to build PSF matching kernel
        lsst::pex::policy::Policy const& _policy;           ///< Policy file for operations

        /** Results from single Kernel model
         */
        boost::shared_ptr<lsst::afw::math::Kernel> _kPtr;    ///< Kernel
        boost::shared_ptr<lsst::afw::math::Kernel> _kErrPtr; ///< Uncertainty in Kernel
        double _kSum;                                        ///< Kernel sum
        double _bg;                                          ///< Differential background value
        double _bgErr;                                       ///< Uncertainty in background
        boost::shared_ptr<ImageStatistics<lsst::afw::image::MaskedImage<ImageT> > > _kStats; 
                                                             ///< Home-grown statistics; placeholder for Sdqa

    }; // end of class

}}}

#endif // LSST_IP_DIFFIM_SPATIALMODELKERNEL_H

