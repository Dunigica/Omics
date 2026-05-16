import pandas as pd
import numpy as np
import glob


class ChemCompound(object):
    def __init__(self):
        self.dataId=""
        self.properties=CompoundGeneralProperties()
        self.summary=CompoundSummary()
        self.compoundStructure=CompoundStructure()

  

class CompoundGeneralProperties(object):
    def __init(self):
        self.id=None
        self.Name=None
        self.MW=None
        self.HBDC=None
        self.HBAC=None
        self.TFC=None
        self.MF=None



class CompoundSummary(object):
    def __init(self):
        self.CID=""
        self.IUPACName=""
        self.MF=""
        self.SummaryName=""
        

class CompoundStructure(object):
    def __init__(self):
        self.cid=""
        self.aid=""
        self.elements=list()
        self.stereo=list()
        self.bonds=Bonds()
        self.coords=Coords()
        self.compoundStructuralProperties=CompoundStructuralProperties()

 

class Bonds(object):
    def __init__(self):
        self.aid1=list()
        self.aid2=list()
        self.order=list()
    
 
class Stereo(object):
    def StereoFactory(type="Tetrahedral"):
        Stereo={
            "Tetrahedral":StereoTetrahedral,
            "Planar": StereoPlanar
            }
        return Stereo[type]()


class StereoTetrahedral(object):
    def __init__(self):
        self.name=None
        self.type=None
        self.parity=None
        self.center=None #int
        self.above=None
        self.top=None
        self.bottom=None
        self.below=None

class StereoPlanar(object):
    def __init__(self):
        self.left=None
        self.ltop=None
        self.lbottom=None
        self.right=None 
        self.rtop=None
        self.rbottom=None
        self.type=None
        self.parity=None
        




class Coords(object):
    def __init__(self):
        self.info=None
        self.aid=list()
        self.x=list()
        self.y=list()
        self.Annotation=list()
        self.aid1=list()
        self.aid2=list()

   


class CompoundStructuralProperties(object):
    def __init__(self):
        self.COMPOUND_CANONICALIZED =None #string
        self.PUBCHEM_CACTVS_COMPLEXITY =None #string
        self.PUBCHEM_CACTVS_HBOND_ACCEPTOR =None #int
        self.PUBCHEM_CACTVS_HBOND_DONOR =None #int
        self.PUBCHEM_CACTVS_ROTATABLE_BOND =None  #int
        self.PUBCHEM_CACTVS_SUBSKEYS =None #string
        self.PUBCHEM_IUPAC_OPENEYE_NAME =None #string
        self.PUBCHEM_IUPAC_CAS_NAME =None #string
        self.PUBCHEM_IUPAC_NAME_MARKUP =None #string
        self.PUBCHEM_IUPAC_NAME =None #string
        self.PUBCHEM_IUPAC_SYSTEMATIC_NAME =None #string
        self.PUBCHEM_IUPAC_TRADITIONAL_NAME =None #string
        self.PUBCHEM_IUPAC_INCHI =None #string
        self.PUBCHEM_IUPAC_INCHIKEY =None #string
        self.PUBCHEM_EXACT_MASS=None #string
        self.PUBCHEM_MOLECULAR_FORMULA =None #string
        self.PUBCHEM_MOLECULAR_WEIGHT =None #string
        self.PUBCHEM_OPENEYE_CAN_SMILES =None #string
        self.PUBCHEM_OPENEYE_ISO_SMILES =None #string
        self.PUBCHEM_CACTVS_TPSA =None #string
        self.PUBCHEM_MONOISOTOPIC_WEIGHT =None #string


        #self.PUBCHEM_TOTAL_CHARGE =None #double
        self.PUBCHEM_HEAVY_ATOM_COUNT =None #int
        self.PUBCHEM_ATOM_CHIRAL_COUNT =None #int
        self.PUBCHEM_ATOM_DEF_STEREO_COUNT =None #int
        self.PUBCHEM_ATOM_UDEF_STEREO_COUNT =None #int
        self.PUBCHEM_BOND_CHIRAL_COUNT =None #int
        self.PUBCHEM_BOND_DEF_STEREO_COUNT =None  #int
        self.PUBCHEM_BOND_UDEF_STEREO_COUNT =None #int
        self.PUBCHEM_ISOTOPIC_ATOM_COUNT=None #int

        self.PUBCHEM_COMPONENT_COUNT=None #int
        self.PUBCHEM_CACTVS_TAUTO_COUNT=None #int // can be negative -1
        #PUBCHEM_COORDINATE_TYPE =None #int  // three numbers array


