// -*- lsst-c++ -*-
/**
 * @file ImageSubtract.cc
 *
 * @brief Implementation of image subtraction functions declared in ImageSubtract.h
 *
 * @author Andrew Becker, University of Washington
 *
 * @ingroup ip_diffim
 */
#include <iostream>
#include <limits>
#include <boost/timer.hpp> 

#include <Eigen/Core>

// NOTE -  trace statements >= 6 can ENTIRELY kill the run time
// #define LSST_MAX_TRACE 5

#include <lsst/ip/diffim/ImageSubtract.h>
#include <lsst/afw/image.h>
#include <lsst/afw/math.h>
#include <lsst/pex/exceptions/Exception.h>
#include <lsst/pex/logging/Trace.h>
#include <lsst/pex/logging/Log.h>
#include <lsst/afw/detection/Footprint.h>
#include <lsst/afw/math/ConvolveImage.h>

namespace exceptions = lsst::pex::exceptions; 
namespace logging    = lsst::pex::logging; 
namespace image      = lsst::afw::image;
namespace math       = lsst::afw::math;
namespace detection  = lsst::afw::detection;
namespace diffim     = lsst::ip::diffim;

/**
 * @brief Turns Image into a 2-D Eigen Matrix
 */
template <typename PixelT>
Eigen::MatrixXd diffim::imageToEigenMatrix(
    lsst::afw::image::Image<PixelT> const &img
    ) {
    unsigned int rows = img.getHeight();
    unsigned int cols = img.getWidth();
    Eigen::MatrixXd M = Eigen::MatrixXd::Zero(rows, cols);
    for (int y = 0; y != img.getHeight(); ++y) {
        int x = 0;
        for (typename lsst::afw::image::Image<PixelT>::x_iterator ptr = img.row_begin(y); ptr != img.row_end(y); ++ptr, ++x) {
            // M is addressed row, col
            M(y,x) = *ptr;
        }
    }
    return M;
}
    

/**
 * @brief Adds a Function to an Image
 *
 * @note This routine assumes that the pixel coordinates start at (0, 0) which is
 * in general not true
 *
 */
template <typename PixelT>
void diffim::addSomethingToImage(lsst::afw::image::Image<PixelT> &image,
                                 lsst::afw::math::Function2<double> const &function
    ) {
    
    // Set the pixels row by row, to avoid repeated checks for end-of-row
    for (int y = 0; y != image.getHeight(); ++y) {
        double yPos = image::positionToIndex(y);
        double xPos = image::positionToIndex(0);
        for (typename image::Image<PixelT>::x_iterator ptr = image.row_begin(y), end = image.row_end(y);
             ptr != end; ++ptr, ++xPos) {            
            *ptr += function(xPos, yPos);
        }
    }
}

/**
 * @brief Adds a scalar to an Image
 */
template <typename PixelT>
void diffim::addSomethingToImage(image::Image<PixelT> &image,
                                 double value
    ) {
    if (value != 0.0) {
        image += value;
    }
}

/** 
 * @brief Implement fundamental difference imaging step of convolution and
 * subtraction : D = I - (K*T + bg) where * denotes convolution
 * 
 * @note If you convolve the science image, D = (K*I + bg) - T, set invert=False
 *
 * @note The template is taken to be an MaskedImage; this takes c 1.6 times as long
 * as using an Image
 *
 * @return Difference image
 *
 * @ingroup diffim
 */
template <typename PixelT, typename BackgroundT>
image::MaskedImage<PixelT> diffim::convolveAndSubtract(
    lsst::afw::image::MaskedImage<PixelT> const &imageToConvolve,    ///< Image T to convolve with Kernel
    lsst::afw::image::MaskedImage<PixelT> const &imageToNotConvolve, ///< Image I to subtract convolved template from
    lsst::afw::math::Kernel const &convolutionKernel,                ///< PSF-matching Kernel used for convolution
    BackgroundT background,                                          ///< Differential background function or scalar
    bool invert                                                      ///< Invert the output difference image
    ) {

    boost::timer t;
    t.restart();

    image::MaskedImage<PixelT> convolvedMaskedImage(imageToConvolve.getDimensions());
    convolvedMaskedImage.setXY0(imageToConvolve.getXY0());
    math::convolve(convolvedMaskedImage, imageToConvolve, convolutionKernel, false);
    
    /* Add in background */
    addSomethingToImage(*(convolvedMaskedImage.getImage()), background);
    
    /* Do actual subtraction */
    convolvedMaskedImage -= imageToNotConvolve;

    /* Invert */
    if (invert) {
        convolvedMaskedImage *= -1.0;
    }

    double time = t.elapsed();
    logging::TTrace<5>("lsst.ip.diffim.convolveAndSubtract", 
                       "Total compute time to convolve and subtract : %.2f s", time);

    return convolvedMaskedImage;
}

/** 
 * @brief Implement fundamental difference imaging step of convolution and
 * subtraction : D = I - (K.x.T + bg)
 *
 * @note The template is taken to be an Image, not a MaskedImage; it therefore
 * has neither variance nor bad pixels
 *
 * @note If you convolve the science image, D = (K*I + bg) - T, set invert=False
 * 
 * @return Difference image
 *
 * @ingroup diffim
 */
template <typename PixelT, typename BackgroundT>
image::MaskedImage<PixelT> diffim::convolveAndSubtract(
    lsst::afw::image::Image<PixelT> const &imageToConvolve,          ///< Image T to convolve with Kernel
    lsst::afw::image::MaskedImage<PixelT> const &imageToNotConvolve, ///< Image I to subtract convolved template from
    lsst::afw::math::Kernel const &convolutionKernel,                ///< PSF-matching Kernel used for convolution
    BackgroundT background,                                          ///< Differential background function or scalar
    bool invert                                                      ///< Invert the output difference image
    ) {
    
    boost::timer t;
    t.restart();

    image::MaskedImage<PixelT> convolvedMaskedImage(imageToConvolve.getDimensions());
    convolvedMaskedImage.setXY0(imageToConvolve.getXY0());
    math::convolve(*convolvedMaskedImage.getImage(), imageToConvolve, convolutionKernel, false);
    
    /* Add in background */
    addSomethingToImage(*convolvedMaskedImage.getImage(), background);
    
    /* Do actual subtraction */
    *convolvedMaskedImage.getImage() -= *imageToNotConvolve.getImage();

    /* Invert */
    if (invert) {
        *convolvedMaskedImage.getImage() *= -1.0;
    }
    *convolvedMaskedImage.getMask() <<= *imageToNotConvolve.getMask();
    *convolvedMaskedImage.getVariance() <<= *imageToNotConvolve.getVariance();
    
    double time = t.elapsed();
    logging::TTrace<5>("lsst.ip.diffim.convolveAndSubtract", 
                       "Total compute time to convolve and subtract : %.2f s", time);

    return convolvedMaskedImage;
}

/** 
 * @brief Runs Detection on a single image for significant peaks, and checks
 * returned Footprints for Masked pixels.
 *
 * @note Accepts two MaskedImages, one of which is to be convolved to match the
 * other.  The Detection package is run on the image to be convolved
 * (assumed to be higher S/N than the other image).  The subimages
 * associated with each returned Footprint in both images are checked for
 * Masked pixels; Footprints containing Masked pixels are rejected.  The
 * Footprints are grown by an amount specified in the Policy.  The
 * acceptible Footprints are returned in a vector.
 *
 * @return Vector of "clean" Footprints around which Image Subtraction
 * Kernels will be built.
 *
 */
template <typename PixelT>
std::vector<lsst::afw::detection::Footprint::Ptr> diffim::getCollectionOfFootprintsForPsfMatching(
    lsst::afw::image::MaskedImage<PixelT> const &imageToConvolve,    
    lsst::afw::image::MaskedImage<PixelT> const &imageToNotConvolve, 
    lsst::pex::policy::Policy             const &policy                                       
    ) {
    
    // Parse the Policy
    unsigned int fpNpixMin      = policy.getInt("fpNpixMin");
    unsigned int fpNpixMax      = policy.getInt("fpNpixMax");

    int const kCols             = policy.getInt("kernelCols");
    int const kRows             = policy.getInt("kernelRows");
    double fpGrowKsize          = policy.getDouble("fpGrowKsize");

    int minCleanFp              = policy.getInt("minCleanFp");
    double detThreshold         = policy.getDouble("detThreshold");
    double detThresholdScaling  = policy.getDouble("detThresholdScaling");
    double detThresholdMin      = policy.getDouble("detThresholdMin");
    std::string detThresholdType = policy.getString("detThresholdType");

    // New mask plane that tells us which pixels are already in sources
    // Add to both images so mask planes are aligned
    int diffimMaskPlane = imageToConvolve.getMask()->addMaskPlane(diffim::diffimStampCandidateStr);
    (void)imageToNotConvolve.getMask()->addMaskPlane(diffim::diffimStampCandidateStr);
    image::MaskPixel const diffimBitMask = imageToConvolve.getMask()->getPlaneBitMask(diffim::diffimStampCandidateStr);

    // Add in new plane that will tell us which ones are used
    (void)imageToConvolve.getMask()->addMaskPlane(diffim::diffimStampUsedStr);
    (void)imageToNotConvolve.getMask()->addMaskPlane(diffim::diffimStampUsedStr);

    // Number of pixels to grow each Footprint, based upon the Kernel size
    int fpGrowPix = int(fpGrowKsize * ((kCols > kRows) ? kCols : kRows));

    // List of Footprints
    std::vector<detection::Footprint::Ptr> footprintListIn;
    std::vector<detection::Footprint::Ptr> footprintListOut;

    // Functors to search through the images for masked pixels within candidate footprints
    diffim::FindSetBits<image::Mask<image::MaskPixel> > itcFunctor(*(imageToConvolve.getMask())); 
    diffim::FindSetBits<image::Mask<image::MaskPixel> > itncFunctor(*(imageToNotConvolve.getMask())); 
 
    int nCleanFp = 0;
    while ((nCleanFp < minCleanFp) and (detThreshold > detThresholdMin)) {
        imageToConvolve.getMask()->clearMaskPlane(diffimMaskPlane);
        imageToNotConvolve.getMask()->clearMaskPlane(diffimMaskPlane);

        footprintListIn.clear();
        footprintListOut.clear();
        
        // Find detections
        detection::Threshold threshold = 
                detection::createThreshold(detThreshold, detThresholdType);
        detection::FootprintSet<PixelT> footprintSet(
                imageToConvolve, 
                threshold,
                "",
                fpNpixMin);
        
        // Get the associated footprints
        footprintListIn = footprintSet.getFootprints();
        logging::TTrace<4>("lsst.ip.diffim.getCollectionOfFootprintsForPsfMatching", 
                           "Found %d total footprints above threshold %.3f",
                           footprintListIn.size(), detThreshold);

        // Iterate over footprints, look for "good" ones
        nCleanFp = 0;
        for (std::vector<detection::Footprint::Ptr>::iterator i = footprintListIn.begin(); i != footprintListIn.end(); ++i) {
            // footprint has too many pixels
            if (static_cast<unsigned int>((*i)->getNpix()) > fpNpixMax) {
                logging::TTrace<6>("lsst.ip.diffim.getCollectionOfFootprintsForPsfMatching", 
                               "Footprint has too many pix: %d (max =%d)", 
                               (*i)->getNpix(), fpNpixMax);
                continue;
            } 
            
            logging::TTrace<8>("lsst.ip.diffim.getCollectionOfFootprintsForPsfMatching", 
                               "Footprint in : %d,%d -> %d,%d",
                               (*i)->getBBox().getX0(), (*i)->getBBox().getX1(), 
                               (*i)->getBBox().getY0(), (*i)->getBBox().getY1());

            logging::TTrace<8>("lsst.ip.diffim.getCollectionOfFootprintsForPsfMatching", 
                               "Grow by : %d pixels", fpGrowPix);

            /* Grow the footprint
               flag true  = isotropic grow   = slow
               flag false = 'manhattan grow' = fast
               
               The manhattan masks are rotated 45 degree w.r.t. the coordinate
               system.  They intersect the vertices of the rectangle that would
               connect pixels (X0,Y0) (X1,Y0), (X0,Y1), (X1,Y1).
               
               The isotropic masks do take considerably longer to grow and are
               basically elliptical.  X0, X1, Y0, Y1 delimit the extent of the
               ellipse.

               In both cases, since the masks aren't rectangles oriented with
               the image coordinate system, when we DO extract such rectangles
               as subimages for kernel fitting, some corner pixels can be found
               in multiple subimages.

            */
            detection::Footprint::Ptr fpGrow = 
                detection::growFootprint(*i, fpGrowPix, false);
            
            logging::TTrace<6>("lsst.ip.diffim.getCollectionOfFootprintsForPsfMatching", 
                               "Footprint out : %d,%d -> %d,%d (center %d,%d)",
                               (*fpGrow).getBBox().getX0(), (*fpGrow).getBBox().getY0(),
			       (*fpGrow).getBBox().getX1(), (*fpGrow).getBBox().getY1(),
			       int(0.5 * ((*i)->getBBox().getX0()+(*i)->getBBox().getX1())),
			       int(0.5 * ((*i)->getBBox().getY0()+(*i)->getBBox().getY1())));


            // Ignore if its too close to the edge of the amp image 
            // Note we need to translate to pixel coordinates here
            image::BBox fpBBox = (*fpGrow).getBBox();
            fpBBox.shift(-imageToConvolve.getX0(), -imageToConvolve.getY0());
            if (((*fpGrow).getBBox().getX0() < 0) ||
                ((*fpGrow).getBBox().getY0() < 0) ||
                ((*fpGrow).getBBox().getX1() > imageToConvolve.getWidth()) ||
                ((*fpGrow).getBBox().getY1() > imageToConvolve.getHeight()))
                continue;


            // Grab a subimage; report any exception
            try {
                image::MaskedImage<PixelT> subImageToConvolve(imageToConvolve, fpBBox);
                image::MaskedImage<PixelT> subImageToNotConvolve(imageToNotConvolve, fpBBox);
            } catch (exceptions::Exception& e) {
                logging::TTrace<6>("lsst.ip.diffim.getCollectionOfFootprintsForPsfMatching",
                                   "Exception caught extracting Footprint");
                logging::TTrace<7>("lsst.ip.diffim.getCollectionOfFootprintsForPsfMatching",
                                   e.what());
                continue;
            }

            // Search for any masked pixels within the footprint
            itcFunctor.apply(*fpGrow);
            if (itcFunctor.getBits() > 0) {
                logging::TTrace<6>("lsst.ip.diffim.getCollectionOfFootprintsForPsfMatching", 
                                   "Footprint has masked pix (val=%d) in image to convolve", itcFunctor.getBits()); 
                continue;
            }

            itncFunctor.apply(*fpGrow);
            if (itncFunctor.getBits() > 0) {
                logging::TTrace<6>("lsst.ip.diffim.getCollectionOfFootprintsForPsfMatching", 
                                   "Footprint has masked pix (val=%d) in image not to convolve", itncFunctor.getBits());
                continue;
            }

            // If we get this far, we have a clean footprint
            footprintListOut.push_back(fpGrow);
            (void)detection::setMaskFromFootprint(&(*imageToConvolve.getMask()), *fpGrow, diffimBitMask);
            (void)detection::setMaskFromFootprint(&(*imageToNotConvolve.getMask()), *fpGrow, diffimBitMask);
            nCleanFp += 1;
        }
        detThreshold *= detThresholdScaling;
    }
    imageToConvolve.getMask()->clearMaskPlane(diffimMaskPlane);
    imageToNotConvolve.getMask()->clearMaskPlane(diffimMaskPlane);

    if (footprintListOut.size() == 0) {
      throw LSST_EXCEPT(exceptions::Exception, 
			"Unable to find any footprints for Psf matching");
    }

    logging::TTrace<1>("lsst.ip.diffim.getCollectionOfFootprintsForPsfMatching", 
                       "Found %d clean footprints above threshold %.3f",
                       footprintListOut.size(), detThreshold/detThresholdScaling);
    
    return footprintListOut;
}

// Explicit instantiations
template 
Eigen::MatrixXd diffim::imageToEigenMatrix(lsst::afw::image::Image<float> const &);

template 
Eigen::MatrixXd diffim::imageToEigenMatrix(lsst::afw::image::Image<double> const &);

template class diffim::FindSetBits<image::Mask<> >;
template class diffim::ImageStatistics<float>;
template class diffim::ImageStatistics<double>;

/* */

#define p_INSTANTIATE_convolveAndSubtract(TEMPLATE_IMAGE_T, TYPE)     \
    template \
    image::MaskedImage<TYPE> diffim::convolveAndSubtract( \
        image::TEMPLATE_IMAGE_T<TYPE> const& imageToConvolve, \
        image::MaskedImage<TYPE> const& imageToNotConvolve, \
        math::Kernel const& convolutionKernel, \
        double background, \
        bool invert);      \
    \
    template \
    image::MaskedImage<TYPE> diffim::convolveAndSubtract( \
        image::TEMPLATE_IMAGE_T<TYPE> const& imageToConvolve, \
        image::MaskedImage<TYPE> const& imageToNotConvolve, \
        math::Kernel const& convolutionKernel, \
        math::Function2<double> const& backgroundFunction, \
        bool invert); \

#define INSTANTIATE_convolveAndSubtract(TYPE) \
p_INSTANTIATE_convolveAndSubtract(Image, TYPE) \
p_INSTANTIATE_convolveAndSubtract(MaskedImage, TYPE)
/*
 * Here are the instantiations.
 *
 * Do we really need double diffim code?  It isn't sufficient to remove it here; you'll have to also remove at
 * least SpatialModelKernel<double> and swig instantiations thereof
 */
INSTANTIATE_convolveAndSubtract(float);
INSTANTIATE_convolveAndSubtract(double);

/* */


template
std::vector<detection::Footprint::Ptr> diffim::getCollectionOfFootprintsForPsfMatching(
    image::MaskedImage<float> const &,
    image::MaskedImage<float> const &,
    lsst::pex::policy::Policy const &);

template
std::vector<detection::Footprint::Ptr> diffim::getCollectionOfFootprintsForPsfMatching(
    image::MaskedImage<double> const &,
    image::MaskedImage<double> const &,
    lsst::pex::policy::Policy  const &);

template 
void diffim::addSomethingToImage(
    image::Image<float> &,
    math::Function2<double> const &
    );
template 
void diffim::addSomethingToImage(
    image::Image<double> &,
    math::Function2<double> const &
    );

template 
void diffim::addSomethingToImage(
    image::Image<float> &,
    double
    );
template 
void diffim::addSomethingToImage(
    image::Image<double> &,
    double
    );
