import pandas as pd
import numpy as np
import glob
from ChemCompound import Stereo,StereoTetrahedral,StereoPlanar
from ChemCompound import ChemCompound,CompoundStructure,CompoundSummary,CompoundGeneralProperties,CompoundStructuralProperties,Bonds,Coords

#from codecs import StreamReader


class LoadCompoundStructure:
    @classmethod
    def Load(self,path):
        CompoundStruct =  list()  # List<ChemCompound>
        c = 0
        line="START"
        temp_drug_comp = ChemCompound()
        temp_rug_struct = CompoundStructure()
        try:
            sr = open(path, "r") 
            line = sr.readline()
            #Continue to read until you reach end of file
            while (line != ''):                    
                if ("id cid" in line):
                    temp_drug_comp =  ChemCompound()
                    temp_rug_struct =  CompoundStructure()
                    split_line = line.replace("\n","").split(" ")
                    temp_rug_struct.cid = split_line[ - 1]
                #read atoms
                elif ("atoms {" in line):              
                    line = sr.readline()
                    while ("}," not in line):
                        if ("aid {" in line):                       
                            aid =  list()
                            line = sr.readline()
                            while ("}," not in line):
                                split_line = line.replace("\n","").split(" ")
                                aid.append(int(split_line[ - 1].replace(",", "")))
                                line = sr.readline()                            
                            temp_rug_struct.aid = aid                   
                        elif ("element {" in line):                        
                            elements = list()
                            line = sr.readline()
                            while ("}"not in line):                           
                                split_line = line.replace("\n","").split(" ")
                                elements.append(split_line[ - 1].replace(",", ""))                                                
                                line = sr.readline()                            
                            temp_rug_struct.elements = elements                       
                        line = sr.readline()                   
                #read bonds
                elif ("bonds {" in line):               
                    temp_bonds = Bonds()
                    line = sr.readline()
                    while ("}," not in line):                   
                        if ("aid1 {"  in line):                       
                            aid1 = list()
                            line = sr.readline()
                            while ("}," not in line):                            
                                split_line = line.replace("\n","").split(" ")
                                aid1.append(int(split_line[ - 1].replace(",", "")))
                                line = sr.readline()
                            temp_bonds.aid1 = aid1
                        elif ("aid2 {" in line):                        
                            aid2 = list()
                            line = sr.readline()
                            while ("}," not in line):                           
                                split_line = line.replace("\n","").split(" ")
                                aid2.append(int(split_line[ - 1].replace(",", "")))
                                line = sr.readline()                            
                            temp_bonds.aid2 = aid2                       
                        elif ("order {" in line):                       
                            order = list()
                            line = sr.readline()
                            while ("}" not in line):                           
                                split_line = line.replace("\n","").split(" ")
                                order.append(split_line[ - 1].replace(",", ""))
                                line = sr.readline()                            
                            temp_bonds.order = order                       
                        line = sr.readline()                    
                    temp_rug_struct.bonds = temp_bonds                
                #read stereo
                elif ("stereo {" in line):                
                    all_stereos =list()
                    line = sr.readline()
                    while ("}," not in line):                    
                        if (("{" in line) & (line.replace("\n","").split(" ")[ - 2] =="tetrahedral")):                        
                            curr_stereo =  Stereo.StereoFactory("Tetrahedral")
                            curr_stereo.name = line.replace("\n","").split(" ")[ - 2]
                            line = sr.readline()
                            while ("}" not in line):                           
                                if ("center" in line):                                
                                    split_line = line.replace("\n","").split(" ")
                                    curr_stereo.center = int(split_line[ - 1].replace(",", ""))                                
                                elif ("above" in line):                              
                                    split_line = line.replace("\n","").split(" ")
                                    curr_stereo.above = int(split_line[- 1].replace(",", ""))                                
                                elif ("top" in line):                               
                                    split_line = line.replace("\n","").split(" ")
                                    curr_stereo.top = int(split_line[ - 1].replace(",", ""))                               
                                elif ("bottom" in line):                               
                                    split_line = line.replace("\n","").split(" ")
                                    curr_stereo.bottom = int(split_line[ - 1].replace(",", ""))                               
                                elif ("below" in line):                                
                                    split_line = line.replace("\n","").split(" ")
                                    curr_stereo.below = int(split_line[ - 1].replace(",", ""))                              
                                elif ("parity" in line):                                
                                    split_line = line.replace("\n","").split(" ")
                                    curr_stereo.parity = split_line[ - 1].replace(",", "")                               
                                elif ("type" in line):                               
                                    split_line = line.replace("\n","").split(" ")
                                    curr_stereo.type = split_line[ - 1].replace(",", "")                                
                                line = sr.readline()                            
                            all_stereos.append(curr_stereo)   
                        elif (("{" in line) & (line.replace("\n","").split(" ")[ - 2] =="planar")):                        
                            curr_stereo =  Stereo.StereoFactory("Planar")
                            curr_stereo.name = line.replace("\n","").split(" ")[ - 2]
                            line = sr.readline()
                            while ("}" not in line):  
                                if ("right" in line):                                
                                    split_line = line.replace("\n","").split(" ")
                                    curr_stereo.right = int(split_line[ - 1].replace(",", "")) 
                                elif ("left" in line):                                
                                    split_line = line.replace("\n","").split(" ")
                                    curr_stereo.left = int(split_line[ - 1].replace(",", ""))                                
                                elif ("rtop" in line):                              
                                    split_line = line.replace("\n","").split(" ")
                                    curr_stereo.rtop = int(split_line[- 1].replace(",", ""))                                
                                elif ("ltop" in line):                               
                                    split_line = line.replace("\n","").split(" ")
                                    curr_stereo.ltop = int(split_line[ - 1].replace(",", ""))                               
                                elif ("lbottom" in line):                               
                                    split_line = line.replace("\n","").split(" ")
                                    curr_stereo.lbottom = int(split_line[ - 1].replace(",", ""))                               
                                elif ("rbottom" in line):                                
                                    split_line = line.replace("\n","").split(" ")
                                    curr_stereo.rbottom = int(split_line[ - 1].replace(",", ""))                              
                                elif ("parity" in line):                                
                                    split_line = line.replace("\n","").split(" ")
                                    curr_stereo.parity = split_line[ - 1].replace(",", "")                               
                                elif ("type" in line):                               
                                    split_line = line.replace("\n","").split(" ")
                                    curr_stereo.type = split_line[ - 1].replace(",", "")                                
                                line = sr.readline()                            
                            all_stereos.append(curr_stereo)  

                        line = sr.readline()                    
                    temp_rug_struct.stereo = all_stereos   
                    print(temp_rug_struct.cid+": "+str(len(all_stereos)))
                #load coords
                elif ("coords {" in line):                
                    temp_coords =  Coords()
                    line = sr.readline()
                    info = ""
                    while ("}," not in line):                    
                        info = info + line
                        line = sr.readline()                   
                    line = sr.readline()
                    temp_coords.info = info
                    if ("aid {" in line):                   
                        aid = list()
                        line = sr.readline()
                        while ("}," not in line):                        
                            split_line = line.replace("\n","").split(" ")
                            aid.append(int(split_line[ - 1].replace(",", "")))
                            line = sr.readline()                        
                        line = sr.readline()
                        temp_coords.aid = aid                    
                    if ("conformers {" in line):                    
                        line = sr.readline()
                        line = sr.readline()
                        while ("}" not in line):    
                            while ("}" not in line):                            
                                if ("x {" in line):                                
                                    line = sr.readline()
                                    x=list()
                                    while (("}" in line) & ("{" in line)):    
                                        x_values=line.split("{")[1].split("}")[0].split(",")
                                        split_line = np.array([int(xv) for xv in x_values] )
                                        x.append(split_line)
                                        line = sr.readline()                                    
                                    temp_coords.x = x                                
                                elif ("y {" in line):                                
                                    line = sr.readline()
                                    y=list()
                                    while (("}" in line) & ("{" in line)):      
                                        y_values=line.split("{")[1].split("}")[0].split(",")
                                        split_line = np.array([int(yv) for yv in y_values] )
                                        y.append(split_line)
                                        line = sr.readline()                                    
                                    temp_coords.y = y                               
                                elif ("style {" in line):                                
                                    line = sr.readline()
                                    while ("}" not in line):                                    
                                        if ("annotation {" in line):                                        
                                            line = sr.readline()
                                            Annotation = list()
                                            while ("}," not in line):                                            
                                                split_line = line.replace("\n","").split(" ")
                                                Annotation.append(split_line[ - 1].replace(",", ""))
                                                line = sr.readline()                                            
                                            temp_coords.Annotation = Annotation                                        
                                        elif ("aid1 {" in line):                                        
                                            line = sr.readline()
                                            aid1=list()
                                            while ("}," not in line):                                            
                                                split_line = line.replace("\n","").split(" ")
                                                aid1.append(int(split_line[ - 1].replace(",", "")))
                                                line = sr.readline()                                            
                                            temp_coords.aid1 = aid1                                        
                                        elif ("aid2 {" in line):                                        
                                            line = sr.readline()
                                            aid2=list()
                                            while ("}" not in line):                                            
                                                split_line = line.replace("\n","").split(" ")
                                                aid2.append(int(split_line[ - 1].replace(",", "")))
                                                line = sr.readline()                                            
                                            temp_coords.aid2 = aid2                                        
                                        line = sr.readline()                                    
                                #close style
                                line = sr.readline()
                            #close extra conformers {}
                            line = sr.readline()
                        #close conformers
                    #close the if conformers in lne
                    temp_rug_struct.coords = temp_coords
                    line = sr.readline() #first coords close
                    line = sr.readline() #second coords close                   

                #close if coords           
                #         
                # struct props                    
                #elif ("charge" in line):                
                #    split_line = line.replace(" ", "").split("charge")
                #    total_charge = split_line[ - 1].replace(",", "")
                #    temp_struct_props =  CompoundStructuralProperties()
                #    temp_struct_props.PUBCHEM_TOTAL_CHARGE = float(total_charge)
                #    line = sr.readline()
                elif ("props" in line):
                    temp_label_name = "" 
                    temp_struct_props =  CompoundStructuralProperties()
                    while (temp_label_name != "Weight" + "MonoIsotopic"):                        
                        line = sr.readline()
                        if ("label" in line):                            
                            name_label_value = LoadCompoundStructure.FindCSPLabelName(sr, line)
                            temp_label_name = name_label_value[1] + name_label_value[0]
                            if ((name_label_value[1] == "Compound") & (name_label_value[0] == "Canonicalized")):                                
                                temp_struct_props.COMPOUND_CANONICALIZED = int(name_label_value[2])                                
                            if ((name_label_value[1] == "Compound Complexity") & (name_label_value[0] == "")):                                
                                temp_struct_props.PUBCHEM_CACTVS_COMPLEXITY = name_label_value[2]                                
                            if ((name_label_value[1] == "Count") & (name_label_value[0] == "Hydrogen Bond Acceptor")):                                
                                temp_struct_props.PUBCHEM_CACTVS_HBOND_ACCEPTOR = int(name_label_value[2])                                
                            if ((name_label_value[1] == "Count") & (name_label_value[0] == "Hydrogen Bond Donor")):                                
                                temp_struct_props.PUBCHEM_CACTVS_HBOND_DONOR = int(name_label_value[2])                                
                            if ((name_label_value[1] == "Count") & (name_label_value[0] == "Rotatable Bond")):                                
                                temp_struct_props.PUBCHEM_CACTVS_ROTATABLE_BOND = int(name_label_value[2])                                
                            if ((name_label_value[1] == "Fingerprint") & (name_label_value[0] == "SubStructure Keys")):                                
                                temp_struct_props.PUBCHEM_CACTVS_SUBSKEYS = name_label_value[2]                                
                            if ((name_label_value[1] == "IUPAC Name") & (name_label_value[0] == "Allowed")):                                
                                temp_struct_props.PUBCHEM_IUPAC_OPENEYE_NAME = name_label_value[2]                               
                            if ((name_label_value[1] == "IUPAC Name") & (name_label_value[0] == "CAS-like Style")):                               
                                temp_struct_props.PUBCHEM_IUPAC_CAS_NAME = name_label_value[2]                                
                            if ((name_label_value[1] == "IUPAC Name") & (name_label_value[0] == "Markup")):                                
                                temp_struct_props.PUBCHEM_IUPAC_NAME_MARKUP = name_label_value[2]                                
                            if ((name_label_value[1] == "IUPAC Name") & (name_label_value[0] == "Preferred")):                                
                                temp_struct_props.PUBCHEM_IUPAC_NAME = name_label_value[2]                               
                            if ((name_label_value[1] == "IUPAC Name") & (name_label_value[0] == "Systematic")):                                
                                temp_struct_props.PUBCHEM_IUPAC_SYSTEMATIC_NAME = name_label_value[2]                                
                            if ((name_label_value[1] == "IUPAC Name") & (name_label_value[0] == "Traditional")):                                
                                temp_struct_props.PUBCHEM_IUPAC_TRADITIONAL_NAME = name_label_value[2]                               
                            if ((name_label_value[1] == "InChI") & (name_label_value[0] == "Standard")):                               
                                temp_struct_props.PUBCHEM_IUPAC_INCHI = name_label_value[2]                                
                            if ((name_label_value[1] == "InChIKey") & (name_label_value[0] == "Standard")):                                
                                temp_struct_props.PUBCHEM_IUPAC_INCHIKEY = name_label_value[2]                                
                            if ((name_label_value[1]== "Mass") & (name_label_value[0] == "Exact")):                                
                                temp_struct_props.PUBCHEM_EXACT_MASS = name_label_value[2]                                
                            if ((name_label_value[1] == "Molecular Formula") & (name_label_value[0] == "")):                                
                                temp_struct_props.PUBCHEM_MOLECULAR_FORMULA = name_label_value[2]                                
                            if ((name_label_value[1] == "Molecular Weight") & (name_label_value[0] == "")):                                
                                temp_struct_props.PUBCHEM_MOLECULAR_WEIGHT = name_label_value[2]                                
                            if ((name_label_value[1] == "SMILES") & (name_label_value[0] == "Canonical")):                               
                                temp_struct_props.PUBCHEM_OPENEYE_CAN_SMILES = name_label_value[2]                                
                            if ((name_label_value[1] == "SMILES") & (name_label_value[0] == "Isomeric")):                                
                                temp_struct_props.PUBCHEM_OPENEYE_ISO_SMILES = name_label_value[2]                                
                            if ((name_label_value[1] == "Topological") & (name_label_value[0] == "Polar Surface Area")):                                
                                temp_struct_props.PUBCHEM_CACTVS_TPSA = name_label_value[2]                                
                            if ((name_label_value[1] == "Weight") & (name_label_value[0] == "MonoIsotopic")):                                
                                temp_struct_props.PUBCHEM_MONOISOTOPIC_WEIGHT = name_label_value[2]
                               
                           
                    # end while  "Weight" + "MonoIsotopic"
                    line = sr.readline()
                    line = sr.readline()
                    if ("count {" in line):                        
                        line = sr.readline()
                        split_line = line.replace("\n","").split(" ")
                        if (split_line[ - 2] == "heavy-atom"):                            
                            h_atom = split_line[ - 1].replace(",", "")
                            temp_struct_props.PUBCHEM_HEAVY_ATOM_COUNT = int(h_atom)                            
                        line = sr.readline()
                        split_line = line.replace("\n","").split(" ")
                        if (split_line[ - 2] == "atom-chiral"):                            
                            h_atom = split_line[ - 1].replace(",", "")
                            temp_struct_props.PUBCHEM_ATOM_CHIRAL_COUNT = int(h_atom)                            
                        line = sr.readline()
                        split_line = line.replace("\n","").split(" ")
                        if (split_line[ - 2] == "atom-chiral-def"):                            
                            h_atom = split_line[ - 1].replace(",", "")
                            temp_struct_props.PUBCHEM_ATOM_DEF_STEREO_COUNT = int(h_atom)                            
                        line = sr.readline()
                        split_line = line.replace("\n","").split(" ")
                        if (split_line[ - 2] == "atom-chiral-undef"):                            
                            h_atom = split_line[ - 1].replace(",", "")
                            temp_struct_props.PUBCHEM_ATOM_UDEF_STEREO_COUNT = int(h_atom)                            
                        line = sr.readline()
                        split_line = line.replace("\n","").split(" ")
                        if (split_line[ - 2] == "bond-chiral"):                            
                            h_atom = split_line[ - 1].replace(",", "")
                            temp_struct_props.PUBCHEM_BOND_CHIRAL_COUNT = int(h_atom)                            
                        line = sr.readline()
                        split_line = line.replace("\n","").split(" ")
                        if (split_line[- 2] == "bond-chiral-def"):                            
                            h_atom = split_line[ - 1].replace(",", "")
                            temp_struct_props.PUBCHEM_BOND_DEF_STEREO_COUNT = int(h_atom)                            
                        line = sr.readline()
                        split_line = line.replace("\n","").split(" ")
                        if (split_line[ - 2] == "bond-chiral-undef"):                            
                            h_atom = split_line[ - 1].replace(",", "")
                            temp_struct_props.PUBCHEM_BOND_UDEF_STEREO_COUNT = int(h_atom)                            
                        line = sr.readline()
                        split_line = line.replace("\n","").split(" ")
                        if (split_line[ - 2] == "isotope-atom"):                            
                            h_atom = split_line[ - 1].replace(",", "")
                            temp_struct_props.PUBCHEM_ISOTOPIC_ATOM_COUNT = int(h_atom)                            
                        line = sr.readline()
                        split_line = line.replace("\n","").split(" ")
                        if (split_line[ - 2] == "covalent-unit"):                            
                            h_atom = split_line[ - 1].replace(",", "")
                            temp_struct_props.PUBCHEM_COMPONENT_COUNT = int(h_atom)                            
                        line = sr.readline()
                        split_line = line.replace("\n","").split(" ")
                        if (split_line[- 2] == "tautomers"):                            
                            h_atom = split_line[ - 1].replace(",", "")
                            temp_struct_props.PUBCHEM_CACTVS_TAUTO_COUNT = int(h_atom)                          
                        
                    temp_rug_struct.compoundStructuralProperties = temp_struct_props
                    line = sr.readline() #first struc prop close
                    temp_drug_comp.compoundStructure = temp_rug_struct
                    CompoundStruct.append(temp_drug_comp)                  
                                        
                c = c + 1
                line = sr.readline()                 
                 
        except:        
            print("Exception: ")        
        return CompoundStruct


    def FindCSPLabelName(sri, label_line): # StreamReader,string 
        split_line = label_line.split('"') #.Replace(" ", "")
        label = split_line[ - 2].replace(",", "")
        line = sri.readline()
        name = ""
        if ("name" in line):        
            split_line_name = line.split('"') #.replace(" ", "")
            name = split_line_name[ - 2].replace(",", "")     
        value_line = ""
        actual_value = ""
        while  (value_line != "value"):       
            line = sri.readline()
            if ("value" in line):            
                split_line_all = line.replace("\n", "").split(" ")
                valueIndex =np.where(np.array(split_line_all)=="value")[0][0] 
                value_line = split_line_all[valueIndex]
                subline = split_line_all[ valueIndex+ 2:]                
                actual_value = "".join(subline)   #.Replace(",", "")       
        line = sri.readline()
        while ( ("}," not in line) &("}" not in line)):        
            line = line.replace(" ", "")
            actual_value = actual_value + line
            line = sri.readline()        
        three_values = [name,label,actual_value]
        return three_values
        


