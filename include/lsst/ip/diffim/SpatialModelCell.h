// -*- lsst-c++ -*-
/**
 * @file SpatialModelCell.h
 *
 * @brief Class to ensure constraints for spatial modeling
 *
 * @author Andrew Becker, University of Washington
 *
 * @ingroup ip_diffim
 */

#ifndef LSST_IP_DIFFIM_SPATIALMODELCELL_H
#define LSST_IP_DIFFIM_SPATIALMODELCELL_H

#include <vector>
#include <string>

#include <boost/shared_ptr.hpp>

#include <lsst/detection/Footprint.h>
#include <lsst/daf/base/Persistable.h>
#include <lsst/daf/data/LsstBase.h>

namespace lsst {
namespace ip {
namespace diffim {

    /** 
     * 
     * @brief Class to ensure constraints for spatial modeling
     * 
     * A given MaskedImage will be divided up into cells, with each cell
     * represented by an instance of this class.  Each cell itself contains a
     * list of instances of classes derived from SpatialModelBase.  One member
     * from each cell will be fit for a spatial model.  In case of a poor fit,
     * the next SpatialModelBase instance in the list will be fit for.  If all
     * instances in a list are rejected from the spatial model, the best one
     * will be used.
     */
    template <typename ImageT, typename MaskT, class ModelT>
    class SpatialModelCell: public lsst::daf::base::Persistable,
                            public lsst::daf::data::LsstBase {
        
    public:
        typedef boost::shared_ptr<SpatialModelCell<ImageT, MaskT, ModelT> > Ptr;
        typedef std::vector<typename SpatialModelCell<ImageT, MaskT, ModelT>::Ptr> SpatialModelCellList;

        /** Constructor
         *
         * @param label  string representing "name" of cell
         * @param fpPtrList  vector of pointers to footprints within the cell
         * @param modelPtrList  vector of pointers to models of the function you are fitting for
         */
        SpatialModelCell(std::string label,
                         std::vector<lsst::detection::Footprint::PtrType> fpPtrList, 
                         std::vector<ModelT> modelPtrList);

        /** Constructor
         *
         * @param label  string representing "name" of cell
         * @param colC  effective location of column center of cell within overall MaskedImage
         * @param rowC  effective location of row center of cell within overall MaskedImage
         * @param fpPtrList  vector of pointers to footprints within the cell
         * @param modelPtrList  vector of pointers to models of the function you are fitting for
         */
        SpatialModelCell(std::string label, int colC, int rowC, 
                         std::vector<lsst::detection::Footprint::PtrType> fpPtrList,
                         std::vector<ModelT> modelPtrList);

        /** Destructor
         */
        virtual ~SpatialModelCell() {;};

        /** Get current footprint
         */
        lsst::detection::Footprint::PtrType getCurrentFootprint() {return _fpPtrList[_currentID];};
        
        /** Get current model
         */
        ModelT getCurrentModel() {return _modelPtrList[_currentID];};

        /** Get footprint in list
         * 
         * @param i  index of footprint you want to retrieve
         */
        lsst::detection::Footprint::PtrType getFootprint(int i);

        /** Get model in list
         * 
         * @param i  index of model you want to retrieve
         */
        ModelT getModel(int i);

        /** Get vector of all footprints
         */
        std::vector<lsst::detection::Footprint::PtrType> getFootprints() {return _fpPtrList;};

        /** Get vector of all models
         */
        std::vector<ModelT> getModels() {return _modelPtrList;};

        /** Get number of models
         */
        int  getNModels() {return _nModels;};

        /** Select best model based upon QA assesment
         *
         * @param fix  optionally fix model as the one to use for this cell
         */
        void selectBestModel(bool fix);

        /** Get index of current model
         */
        int  getCurrentID() {return _currentID;};

        /** Set index of current model
         *
         * @param id  index to use; will build model if not built
         */
        void setCurrentID(int id);

        /** Set label
         *
         * @param label  string that represents the label
         */
        void setLabel(std::string label) {_label = label;};

        /** Get label
         */
        std::string getLabel() {return _label;};

        /** Go to next model in list; call its buildModel() method
         */
        bool incrementModel();

        /** Is cell usable for spatial fit; false if no members or all are bad
         */
        bool isUsable();

        /** Is cell usable but the model is fixed?
         */
        bool isFixed() {return _modelIsFixed;};

    private:
        /** @todo Implement method _orderFootprints
         */
        void _orderFootprints();

        std::string _label;       ///< Name of cell for logging/trace
        int _colC;                ///< Effective col position of cell in overall image
        int _rowC;                ///< Effective row position of cell in overall image

        std::vector<lsst::detection::Footprint::PtrType> _fpPtrList; ///< List of footprints in cell
        std::vector<ModelT> _modelPtrList; ///< List of models associated with the footprints

        int _nModels;             ///< Number of entries; len(_fpPtrList)
        int _currentID;           ///< Which entry is being used; 0 <= _currentID < _nModels
        bool _modelIsFixed;       ///< Use model _currentID no matter what

    }; // end of class
 
}}}

#endif // LSST_IP_DIFFIM_SPATIALMODELCELL_H
    
