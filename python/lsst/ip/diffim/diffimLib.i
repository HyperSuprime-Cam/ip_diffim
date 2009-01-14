// -*- lsst-c++ -*-
%define diffimLib_DOCSTRING
"
Python bindings for lsst::ip::diffim code
"
%enddef

%feature("autodoc", "1");
%module(docstring=diffimLib_DOCSTRING, package="lsst.ip.diffim") diffimLib

// Reference for this file is at http://dev.lsstcorp.org/trac/wiki/SwigFAQ 
// Nice practical example is at http://dev.lsstcorp.org/trac/browser/DMS/afw/trunk/python/lsst/afw/image/imageLib.i 

// Suppress swig complaints
#pragma SWIG nowarn=314                 // print is a python keyword (--> _print)
#pragma SWIG nowarn=362                 // operator=  ignored

 // Remove warnings
 // Nothing known about 'boost::bad_any_cast'
namespace boost {
    class bad_any_cast; 
}

/* handle C++ arguments that should be outputs in python */
%apply int& OUTPUT { int& };
%apply float& OUTPUT { float& };
%apply double& OUTPUT { double& };

%{
#include <lsst/ip/diffim/SpatialModelCell.h>
#include <lsst/ip/diffim/SpatialModelBase.h>
#include <lsst/ip/diffim/SpatialModelKernel.h>

#include <lsst/ip/diffim/ImageSubtract.h>
#include <lsst/ip/diffim/wcsMatch.h>
#include <lsst/ip/diffim/Pca.h>
%}

%inline %{
namespace boost {
    typedef unsigned short uint16_t;
    namespace mpl { }
}
%}

/******************************************************************************/

%include "lsst/p_lsstSwig.i"
%include "lsst/daf/base/persistenceMacros.i"
%include "lsst/afw/image/lsstImageTypes.i"
%include "lsst/detection/detectionLib.i"

%pythoncode %{
import lsst.utils

def version(HeadURL = r"$HeadURL$"):
    """Return a version given a HeadURL string. If a different version is setup, return that too"""

    version_svn = lsst.utils.guessSvnVersion(HeadURL)

    try:
        import eups
    except ImportError:
        return version_svn
    else:
        try:
            version_eups = eups.setup("afw")
        except AttributeError:
            return version_svn

    if version_eups == version_svn:
        return version_svn
    else:
        return "%s (setup: %s)" % (version_svn, version_eups)

%}

/******************************************************************************/

%import "lsst/afw/image/imageLib.i" 
%lsst_exceptions();

/******************************************************************************/

%{
#include "lsst/ip/diffim/ImageSubtract.h"
%}

%include "lsst/ip/diffim/ImageSubtract.h"

%template(DifferenceImageStatisticsF)
    lsst::ip::diffim::DifferenceImageStatistics<float, lsst::afw::image::maskPixelType>;
%template(DifferenceImageStatisticsD)
    lsst::ip::diffim::DifferenceImageStatistics<double, lsst::afw::image::maskPixelType>;

%template(convolveAndSubtract)
    lsst::ip::diffim::convolveAndSubtract<float, lsst::afw::image::maskPixelType>;
%template(convolveAndSubtract)
    lsst::ip::diffim::convolveAndSubtract<double, lsst::afw::image::maskPixelType>;

%template(computePsfMatchingKernelForFootprint)
    lsst::ip::diffim::computePsfMatchingKernelForFootprint<float, lsst::afw::image::maskPixelType>;
%template(computePsfMatchingKernelForFootprint)
    lsst::ip::diffim::computePsfMatchingKernelForFootprint<double, lsst::afw::image::maskPixelType>;

%template(computePsfMatchingKernelForFootprintGSL)
    lsst::ip::diffim::computePsfMatchingKernelForFootprintGSL<float, lsst::afw::image::maskPixelType>;
%template(computePsfMatchingKernelForFootprintGSL)
    lsst::ip::diffim::computePsfMatchingKernelForFootprintGSL<double, lsst::afw::image::maskPixelType>;

%template(getCollectionOfFootprintsForPsfMatching)
    lsst::ip::diffim::getCollectionOfFootprintsForPsfMatching<float, lsst::afw::image::maskPixelType>;
%template(getCollectionOfFootprintsForPsfMatching)
    lsst::ip::diffim::getCollectionOfFootprintsForPsfMatching<double, lsst::afw::image::maskPixelType>;

%template(maskOk)                           
    lsst::ip::diffim::maskOk<lsst::afw::image::maskPixelType>;

%template(calculateMaskedImageStatistics)
    lsst::ip::diffim::calculateMaskedImageStatistics<float, lsst::afw::image::maskPixelType>;
%template(calculateMaskedStatistics)
    lsst::ip::diffim::calculateMaskedImageStatistics<double, lsst::afw::image::maskPixelType>;

%template(calculateImageStatistics)         lsst::ip::diffim::calculateImageStatistics<float>;
%template(calculateImageStatistics)         lsst::ip::diffim::calculateImageStatistics<double>;
%template(addFunctionToImage)               lsst::ip::diffim::addFunctionToImage<double, double>;
%template(addFunctionToImage)               lsst::ip::diffim::addFunctionToImage<float, double>;
%template(addFunctionToImage)               lsst::ip::diffim::addFunctionToImage<double, float>;
%template(addFunctionToImage)               lsst::ip::diffim::addFunctionToImage<float, float>;

/******************************************************************************/

%{
#include "lsst/ip/diffim/SpatialModelBase.h"
%}

SWIG_SHARED_PTR(SpatialModelBasePtrF, lsst::ip::diffim::SpatialModelBase<float>);
SWIG_SHARED_PTR(SpatialModelBasePtrD, lsst::ip::diffim::SpatialModelBase<double>);

%include "lsst/ip/diffim/SpatialModelBase.h"

%template(SpatialModelBaseF) lsst::ip::diffim::SpatialModelBase<float>;
%template(SpatialModelBaseD) lsst::ip::diffim::SpatialModelBase<double>;

%template(VectorSpatialModelBaseF) std::vector<lsst::ip::diffim::SpatialModelBase<float>* >;
%template(VectorSpatialModelBaseD) std::vector<lsst::ip::diffim::SpatialModelBase<double>* >;

/******************************************************************************/

%{
#include "lsst/ip/diffim/SpatialModelKernel.h"
%}

SWIG_SHARED_PTR_DERIVED(SpatialModelKernelPtrF, 
                        lsst::ip::diffim::SpatialModelBase<float>,
                        lsst::ip::diffim::SpatialModelKernel<float>);
SWIG_SHARED_PTR_DERIVED(SpatialModelKernelPtrD, 
                        lsst::ip::diffim::SpatialModelBase<double>,
                        lsst::ip::diffim::SpatialModelKernel<double>);

%include "lsst/ip/diffim/SpatialModelKernel.h"

%template(SpatialModelKernelF) lsst::ip::diffim::SpatialModelKernel<float>;
%template(SpatialModelKernelD) lsst::ip::diffim::SpatialModelKernel<double>;

%template(VectorSpatialModelKernelF) std::vector<lsst::ip::diffim::SpatialModelKernel<float>* >;
%template(VectorSpatialModelKernelD) std::vector<lsst::ip::diffim::SpatialModelKernel<double>* >;

/******************************************************************************/

%{
#include "lsst/ip/diffim/SpatialModelCell.h"
%}

SWIG_SHARED_PTR(SpatialModelCellPtrF, lsst::ip::diffim::SpatialModelCell<float>);
SWIG_SHARED_PTR(SpatialModelCellPtrD, lsst::ip::diffim::SpatialModelCell<double>);

%include "lsst/ip/diffim/SpatialModelCell.h"

%template(SpatialModelCellF) lsst::ip::diffim::SpatialModelCell<float>;
%template(SpatialModelCellD) lsst::ip::diffim::SpatialModelCell<double>;

%template(VectorSpatialModelCellF) std::vector<lsst::ip::diffim::SpatialModelCell<float>* >;
%template(VectorSpatialModelCellD) std::vector<lsst::ip::diffim::SpatialModelCell<double>* >;

/******************************************************************************/

%{
#include "lsst/ip/diffim/Pca.h"
%}

%include "lsst/ip/diffim/Pca.h"

%template(computePca)                    lsst::ip::diffim::computePca<vw::math::Matrix<float>, vw::math::Vector<float> >;
%template(computePca)                    lsst::ip::diffim::computePca<vw::math::Matrix<double>, vw::math::Vector<double> >;
%template(decomposeMatrixUsingBasis)     lsst::ip::diffim::decomposeMatrixUsingBasis<vw::math::Matrix<float> >;
%template(decomposeMatrixUsingBasis)     lsst::ip::diffim::decomposeMatrixUsingBasis<vw::math::Matrix<double> >;
%template(approximateMatrixUsingBasis)   lsst::ip::diffim::approximateMatrixUsingBasis<vw::math::Matrix<float> >;
%template(approximateMatrixUsingBasis)   lsst::ip::diffim::approximateMatrixUsingBasis<vw::math::Matrix<double> >;

/******************************************************************************/

%{
#include "lsst/ip/diffim/wcsMatch.h"
%}

%include "lsst/ip/diffim/wcsMatch.h"

%template(wcsMatch)    lsst::ip::diffim::wcsMatch<boost::uint16_t, lsst::afw::image::maskPixelType>;
%template(wcsMatch)    lsst::ip::diffim::wcsMatch<float,           lsst::afw::image::maskPixelType>;
%template(wcsMatch)    lsst::ip::diffim::wcsMatch<double,          lsst::afw::image::maskPixelType>;


