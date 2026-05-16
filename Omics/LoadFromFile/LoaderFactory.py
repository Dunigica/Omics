import numpy as np
import pandas as pd
import glob
from ChemCompound import Stereo,StereoTetrahedral,StereoPlanar
from ChemCompound import ChemCompound,CompoundStructure,CompoundSummary,CompoundGeneralProperties,CompoundStructuralProperties,Bonds,Coords

from LoadFromFile.LoadCompoundStructure import LoadCompoundStructure
from LoadFromFile.LoadProteinSequence import LoadProteinSequence


class Loader(object):
    def LoaderFactory(datatype="Compound"):
        Loader={
            "Compound": LoadCompoundStructure,
            "Protein":LoadProteinSequence            
            }
        return Loader[datatype]()
