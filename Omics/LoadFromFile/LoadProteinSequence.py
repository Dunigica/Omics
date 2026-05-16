import pandas as pd
import numpy as np
import glob
from Protein import Protein


class LoadProteinSequence:
    @classmethod
    def Load(self,path):
        ListProtein = list() 
        ProteinHolder = Protein()
        line="START"
        try:            
            #Pass the file path and file name to the StreamReader constructor
            sr=open(path, "r")                
            #Continue to read until you reach end of file            
            while (line!=''):   
                line = sr.readline()
                if (">" in line):
                    ProteinHolder.Info = line
                    ProteinHolder.ProteinName=   line.split(";")[0].split(":")[1].split(" ")[0]         
                if (">" not in line):
                    ProteinHolder.AASequence = line.replace("\n","")
                    ListProtein.append(ProteinHolder)
                    ProteinHolder = Protein()                    
                                
            #end while
            #close the file
            sr.close()
        except: #catch (Exception e)
            print("Exception: "  )       
        finally:
            print("Executing finally block.")

        return ListProtein
