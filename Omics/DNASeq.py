import pandas as pd
import numpy as np
import glob


class DNAseq(object):
    def __init__(self ):
        self.Info = None
        self.SeqName = None
        self.Sequence = None




class Gene(object):
    def __init__(self):
        self.Info = Info
        self.GeneName = geneName
        self.locus = None #string  [locus_tag=hCG_2014181]
        self.dbRef = None #string  //[db_xref=GeneID:1129]
        self.Protein = None #string  //[protein=cholinergic receptor, muscarinic 2]
        self.Partial = None #int    // [partial=3'] 
        self.ProteinId= None #string  //[protein_id=EAW83865.1] 
        self.Location =list()  # List<Array>  //[location=join(34009369..34009494,34011157..34011220,34051978..34052135,34052522..34052710,34053217..34053364,34053718..>34053950)]
        self.GbKey = None #string   //  [gbkey=CDS]
        self.NTSequence = None
 

   
