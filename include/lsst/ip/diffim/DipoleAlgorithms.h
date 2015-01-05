// -*- LSST-C++ -*-

/* 
 * LSST Data Management System
 * Copyright 2008, 2009, 2010 LSST Corporation.
 * 
 * This product includes software developed by the
 * LSST Project (http://www.lsst.org/).
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 * 
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 * 
 * You should have received a copy of the LSST License Statement and 
 * the GNU General Public License along with this program.  If not, 
 * see <http://www.lsstcorp.org/LegalNotices/>.
 */
 
#ifndef LSST_IP_DIFFIM_DIPOLEALGORITHMS_H
#define LSST_IP_DIFFIM_DIPOLEALGORITHMS_H
//!
// Control/algorithm hierarchy for dipole measurement.
//

#include <stdio.h>
#include <execinfo.h>
#include <signal.h>
#include <stdlib.h>
#include <unistd.h>
#include "lsst/base.h"
#include "lsst/pex/config.h"
#include "ndarray/eigen.h"
#include "lsst/afw/table/Source.h"
#include "lsst/meas/base/Algorithm.h"
#include "lsst/meas/base/FluxUtilities.h"
#include "lsst/meas/base/CentroidUtilities.h"
#include "lsst/meas/base/FlagHandler.h"
#include "lsst/meas/base/InputUtilities.h"

namespace lsst {
namespace ip {
namespace diffim {

class DipoleCentroidControl {
public:

    explicit DipoleCentroidControl() {}
};


/**
 *  @brief C++ control object for naive dipole centroid.
 */
class NaiveDipoleCentroidControl : public DipoleCentroidControl {
public:
    NaiveDipoleCentroidControl() : DipoleCentroidControl() {}
};

class DipoleFluxControl {
public:

    explicit DipoleFluxControl() {}
};

/**
 *  @brief C++ control object for naive dipole fluxes.
 */
class NaiveDipoleFluxControl : public DipoleFluxControl {
public:
    NaiveDipoleFluxControl() : DipoleFluxControl() {}
};

/**
 *  @brief C++ control object for PSF dipole fluxes.
 */
class PsfDipoleFluxControl : public DipoleFluxControl {
public:
    LSST_CONTROL_FIELD(maxPixels, int, "Maximum number of pixels to apply the measurement to");
    LSST_CONTROL_FIELD(stepSizeCoord, float, "Default initial step size for coordinates in non-linear fitter");
    LSST_CONTROL_FIELD(stepSizeFlux, float, "Default initial step size for flux in non-linear fitter");
    LSST_CONTROL_FIELD(errorDef, double, "How many sigma the error bars of the non-linear fitter represent");
    LSST_CONTROL_FIELD(maxFnCalls, int, "Maximum function calls for non-linear fitter; 0 = unlimited");
    PsfDipoleFluxControl() : DipoleFluxControl(), maxPixels(500), 
                             stepSizeCoord(0.1), stepSizeFlux(1.0), errorDef(1.0), maxFnCalls(100000) {}
};


/**
 *  @brief Intermediate base class for algorithms that compute a centroid.
 */
class DipoleCentroidAlgorithm {
public:

    enum {
        FAILURE=lsst::meas::base::FlagHandler::FAILURE,
        POS_FAILURE,
        NEG_FAILURE,
        N_FLAGS
    };

    /// A typedef to the Control object for this algorithm, defined above.
    /// The control object contains the configuration parameters for this algorithm.
    typedef DipoleCentroidControl Control;

    DipoleCentroidAlgorithm(Control const & ctrl, std::string const & name,
        afw::table::Schema & schema, std::string const & doc);
    /**
     *  @brief Tuple type that holds the keys that define a standard centroid algorithm.
     *
     *  Algorithms are encouraged to add additional flags as appropriate, but these are required.
     */
    typedef meas::base::CentroidResultKey KeyTuple;

    /// @brief Return the standard centroid keys registered by this algorithm.
    KeyTuple const & getPositiveKeys() const { return _positiveKeys; }
    KeyTuple const & getNegativeKeys() const { return _negativeKeys; }

    virtual void measure(
        afw::table::SourceRecord & measRecord,
        afw::image::Exposure<float> const & exposure
    ) const = 0;

    virtual void fail(
        afw::table::SourceRecord & measRecord,
        lsst::meas::base::MeasurementError * error=NULL
    ) const = 0;

protected:

    /// @brief Initialize with a manually-constructed key tuple.
    DipoleCentroidAlgorithm(Control const & ctrl, std::string const & name, afw::table::Schema & schema,
       std::string const & doc, KeyTuple const & positiveKeys, KeyTuple const & negativeKeys);

    Control _ctrl;
    lsst::meas::base::FluxResultKey _fluxResultKey;
    lsst::meas::base::FlagHandler _flagHandler;
    lsst::meas::base::SafeCentroidExtractor _centroidExtractor;

    // These are private so they doesn't shadow the other overloads in base classes;
    // we can still call it via the public method on the base class.  We could have
    // used a using declaration instead, but Swig had trouble with that here.

    KeyTuple _positiveKeys;
    KeyTuple _negativeKeys;
};



/**
 *  @brief Intermediate base class for algorithms that compute a flux.
 */
class DipoleFluxAlgorithm{
public:
    enum {
        FAILURE=lsst::meas::base::FlagHandler::FAILURE,
        POS_FAILURE,
        NEG_FAILURE,
        N_FLAGS
    };

    /// A typedef to the Control object for this algorithm, defined above.
    /// The control object contains the configuration parameters for this algorithm.
    typedef DipoleFluxControl Control;

    DipoleFluxAlgorithm(Control const & ctrl, std::string const & name, afw::table::Schema & schema,
        std::string const & doc);

    /**
     *  @brief Tuple type that holds the keys that define a standard flux algorithm.
     *
     *  Algorithms are encouraged to add additional flags as appropriate, but these are required.
     */
    typedef lsst::meas::base::FluxResultKey KeyTuple;
    /// @brief Return the standard flux keys registered by this algorithm.
    KeyTuple const & getPositiveKeys() const { return _positiveKeys; }
    KeyTuple const & getNegativeKeys() const { return _negativeKeys; }

    virtual void measure(
        afw::table::SourceRecord & measRecord,
        afw::image::Exposure<float> const & exposure
    ) const = 0;

    virtual void fail(
        afw::table::SourceRecord & measRecord,
        lsst::meas::base::MeasurementError * error=NULL
    ) const = 0;

protected:

    /// @brief Initialize with a manually-constructed key tuple.
    DipoleFluxAlgorithm(DipoleFluxControl const & ctrl, std::string const & name,
                        afw::table::Schema & schema, std::string const & doc,
                        KeyTuple const & positiveKeys, KeyTuple const & negativeKeys);

    /// @brief Initialize using afw::table::addFlux field to fill out repetitive descriptions.
    lsst::meas::base::FluxResultKey _fluxResultKey;
    lsst::meas::base::FlagHandler _flagHandler;
    lsst::meas::base::SafeCentroidExtractor _centroidExtractor;

    // These are private so they doesn't shadow the other overloads in base classes;
    // we can still call it via the public method on the base class.  We could have
    // used a using declaration instead, but Swig had trouble with that here.

    KeyTuple _positiveKeys;
    KeyTuple _negativeKeys;
};

inline DipoleCentroidAlgorithm::DipoleCentroidAlgorithm(
        Control const & ctrl, std::string const & name, afw::table::Schema & schema, std::string const & doc,
        KeyTuple const & positiveKeys, KeyTuple const & negativeKeys
    ) : 
    _centroidExtractor(schema, name, true)
{
    meas::base::CentroidResultKey::addFields(schema, name+"_pos", doc + ": positive lobe", meas::base::SIGMA_ONLY);
    meas::base::CentroidResultKey::addFields(schema, name+"_neg", doc + ": negative lobe", meas::base::SIGMA_ONLY);
    static boost::array<lsst::meas::base::FlagDefinition,N_FLAGS> const flagDefs = {{
        {"flag", "general failure flag, set if anything went wrong"},
        {"pos_flag", "failure flag for positive, set if anything went wrong"},
        {"neg_flag", "failure flag for negative, set if anything went wrong"}
    }};
    _flagHandler = meas::base::FlagHandler::addFields(schema, name, flagDefs.begin(), flagDefs.end());
    _positiveKeys = KeyTuple(schema[name+"_pos"]); 
    _negativeKeys = KeyTuple(schema[name+"_neg"]);
}

inline DipoleCentroidAlgorithm::DipoleCentroidAlgorithm(
    Control const & ctrl, std::string const & name, afw::table::Schema & schema, std::string const & doc
    ) :
    _centroidExtractor(schema, name, true)
{
    static boost::array<lsst::meas::base::FlagDefinition,N_FLAGS> const flagDefs = {{
        {"flag", "general failure flag, set if anything went wrong"},
        {"pos_flag", "failure flag for positive, set if anything went wrong"},
        {"neg_flag", "failure flag for negative, set if anything went wrong"}
    }};
    std::cout << "Make DCA: " << name << "\n";
    _flagHandler = meas::base::FlagHandler::addFields(schema, name, flagDefs.begin(), flagDefs.end());
    meas::base::CentroidResultKey::addFields(schema, name+"_pos", doc+": positive lobe", meas::base::SIGMA_ONLY);
    meas::base::CentroidResultKey::addFields(schema, name+"_neg", doc+": negative lobe", meas::base::SIGMA_ONLY);
    _positiveKeys = KeyTuple(schema[name+"_pos"]); 
    _negativeKeys = KeyTuple(schema[name+"_neg"]);
}

inline DipoleFluxAlgorithm::DipoleFluxAlgorithm(
    DipoleFluxControl const & ctrl, std::string const & name, afw::table::Schema & schema,
        std::string const & doc, KeyTuple const & positiveKeys, KeyTuple const & negativeKeys
    ) :
    _centroidExtractor(schema, name, false)
{
    static boost::array<lsst::meas::base::FlagDefinition,N_FLAGS> const flagDefs = {{
        {"flag", "general failure flag, set if anything went wrong"},
        {"pos_flag", "failure flag for positive, set if anything went wrong"},
        {"neg_flag", "failure flag for negative, set if anything went wrong"}
    }};
    std::cout << "Make DFA: " << name << "\n";
    _flagHandler = meas::base::FlagHandler::addFields(schema, name, flagDefs.begin(), flagDefs.end());
    meas::base::FluxResultKey::addFields(schema, name+"_pos", doc+": positive lobe");
    meas::base::FluxResultKey::addFields(schema, name+"_neg", doc+": negative lobe");
    _positiveKeys = KeyTuple(positiveKeys); 
    _negativeKeys = KeyTuple(negativeKeys); 
}

inline DipoleFluxAlgorithm::DipoleFluxAlgorithm(
    DipoleFluxControl const & ctrl, std::string const & name, afw::table::Schema & schema,
        std::string const & doc
    ) :
    _centroidExtractor(schema, name, false)
{
    static boost::array<lsst::meas::base::FlagDefinition,N_FLAGS> const flagDefs = {{
        {"flag", "general failure flag, set if anything went wrong"},
        {"pos_flag", "failure flag for positive, set if anything went wrong"},
        {"neg_flag", "failure flag for negative, set if anything went wrong"}
    }};
    _flagHandler = meas::base::FlagHandler::addFields(schema, name, flagDefs.begin(), flagDefs.end());
    meas::base::FluxResultKey::addFields(schema, name+"_pos", doc+": positive lobe");
    meas::base::FluxResultKey::addFields(schema, name+"_neg", doc+": negative lobe");
    _positiveKeys = KeyTuple(schema[name+"_pos"]); 
    _negativeKeys = KeyTuple(schema[name+"_neg"]);
}

/*
class that knows how to calculate centroids as a simple unweighted first
 * moment of the 3x3 region around the peaks
 */
class NaiveDipoleFlux : public DipoleFluxAlgorithm {
public:

    NaiveDipoleFlux(NaiveDipoleFluxControl const & ctrl, std::string const & name, afw::table::Schema & schema) :
        DipoleFluxAlgorithm(ctrl, name, schema, "raw flux counts"),
        _ctrl(ctrl),
        _numPositiveKey(schema.addField<int>(name+"_npos", "number of positive pixels", "dn")),
        _numNegativeKey(schema.addField<int>(name+"_nneg", "number of negative pixels", "dn"))
    {
    }

    void measure(
        afw::table::SourceRecord & measRecord,
        afw::image::Exposure<float> const & exposure
    ) const;

    void fail(
        afw::table::SourceRecord & measRecord,
        lsst::meas::base::MeasurementError * error=NULL
    ) const;

protected:

private:

    afw::table::Key<int> _numPositiveKey;
    afw::table::Key<int> _numNegativeKey;
    Control _ctrl;
};

/**
 *  @brief Intermediate base class for algorithms that compute a centroid.
 */
class NaiveDipoleCentroid : public DipoleCentroidAlgorithm { //: public lsst::meas::base::SimpleAlgorithm {
public:

    enum {
        FAILURE=lsst::meas::base::FlagHandler::FAILURE,
        POS_FLAGS,
        NEG_FLAGS,
        N_FLAGS
    };

    /// A typedef to the Control object for this algorithm, defined above.
    /// The control object contains the configuration parameters for this algorithm.
    typedef NaiveDipoleCentroidControl Control;

    NaiveDipoleCentroid(Control const & ctrl, std::string const & name, afw::table::Schema & schema);
    /**
     *  @brief Tuple type that holds the keys that define a standard centroid algorithm.
     *
     *  Algorithms are encouraged to add additional flags as appropriate, but these are required.
     */
    typedef meas::base::CentroidResultKey KeyTuple;

    /// @brief Return the standard centroid keys registered by this algorithm.
    KeyTuple const & getPositiveKeys() const { return _positiveKeys; }
    KeyTuple const & getNegativeKeys() const { return _negativeKeys; }

    // These are private so they doesn't shadow the other overloads in base classes;
    // we can still call it via the public method on the base class.  We could have
    // used a using declaration instead, but Swig had trouble with that here.

    void measure(
        afw::table::SourceRecord & measRecord,
        afw::image::Exposure<float> const & exposure
    ) const;

    void fail(
        afw::table::SourceRecord & measRecord,
        lsst::meas::base::MeasurementError * error=NULL
    ) const;

protected:

    /// @brief Initialize with a manually-constructed key tuple.
    NaiveDipoleCentroid(Control const & ctrl, std::string const & name, afw::table::Schema & schema,
        KeyTuple const & positiveKeys, KeyTuple const & negativeKeys);

    Control _ctrl;
    lsst::meas::base::FluxResultKey _fluxResultKey;
    lsst::meas::base::FlagHandler _flagHandler;
    lsst::meas::base::SafeCentroidExtractor _centroidExtractor;
};




/**
 * Implementation of Psf dipole flux
 */
class PsfDipoleFlux : public DipoleFluxAlgorithm {
public:

    PsfDipoleFlux(PsfDipoleFluxControl const & ctrl, std::string const & name, afw::table::Schema & schema) :
        DipoleFluxAlgorithm(ctrl, name, schema, "jointly fitted psf flux counts"),
        _ctrl(ctrl),
        _chi2dofKey(schema.addField<float>(name+"_chi2dof", 
                                           "chi2 per degree of freedom of fit")),
        _flagMaxPixelsKey(schema.addField<afw::table::Flag>(name+"_flags_maxpix",
                                                            "set if too large a footprint was sent to the algorithm"))
    {
        meas::base::CentroidResultKey::addFields(schema, name+"_pos_centroid", "psf fitted center of positive lobe", meas::base::SIGMA_ONLY);
        meas::base::CentroidResultKey::addFields(schema, name+"_neg_centroid", "psf fitted center of negative lobe", meas::base::SIGMA_ONLY);
        meas::base::CentroidResultKey::addFields(schema, name+"_centroid", "average of negative and positive lobe positions", meas::base::SIGMA_ONLY);
        _posCentroid = lsst::meas::base::CentroidResultKey(schema[name+"_pos_centroid"]); 
        _negCentroid = lsst::meas::base::CentroidResultKey(schema[name+"_neg_centroid"]); 
        _avgCentroid = lsst::meas::base::CentroidResultKey(schema[name+"_centroid"]); 
    }
    std::pair<double,int> chi2(afw::table::SourceRecord & source,
                afw::image::Exposure<float> const & exposure,
                double negCenterX, double negCenterY, double negFlux,
                double posCenterX, double poCenterY, double posFlux
                ) const;

    void measure(
        afw::table::SourceRecord & measRecord,
        afw::image::Exposure<float> const & exposure
    ) const;

    void fail(
        afw::table::SourceRecord & measRecord,
        lsst::meas::base::MeasurementError * error=NULL
    ) const;


private:

    PsfDipoleFluxControl _ctrl;
    afw::table::Key<float> _chi2dofKey;
    lsst::meas::base::CentroidResultKey  _avgCentroid;
    lsst::meas::base::CentroidResultKey  _negCentroid;
    lsst::meas::base::CentroidResultKey  _posCentroid;

    afw::table::Key< afw::table::Flag > _flagMaxPixelsKey;
};

}}}// namespace lsst::ip::diffim

#endif // !LSST_IP_DIFFIM_DIPOLEALGORITHMS_H
