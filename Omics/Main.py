import sys
import argparse
import os
import sys
from LoadFromFile.LoadCompoundStructure import LoadCompoundStructure
from LoadFromFile.LoadProteinSequence import LoadProteinSequence
from ClusterCompounds import KMeansClustering
#from DrugDiscovery.BindingFreeEnergyAfinity.RunFreeEnergyCalc import RunFreeEnergy
import ast

def main():
            
    my_parser = argparse.ArgumentParser() #description='List the content of a folder')
    # Add the arguments for clustering
    my_parser.add_argument('--dataPath', action='store', type=str, required=True, help='compound data file')
    #my_parser.add_argument('--protPath', action='store', type=str, required=True, help='protein data file')
    my_parser.add_argument('--modelType', action='store', type=str, required=True, help='name of ml model to use for model factory')
    my_parser.add_argument('--modelGroup', action='store', type=str, required=True, help='name of ml model group ex:Clustering,Classification, etc')
    my_parser.add_argument('--writePath', action='store', type=str, required=True, help='write results path')
    my_parser.add_argument('--dataType', action='store', type=str, required=True, help='specific data to load for loader Factory')
    my_parser.add_argument('--subdataType', action='store', type=str, required=True, help='specific subdata to use in a model')
    my_parser.add_argument('--solutionComb', action='store', type=str, required=True, help='combination of algorithm and data to use')
    my_parser.add_argument('--params', action='store', type=str, required=True, help='dict of params for the model')
    
    # Add the arguments for Free energy calculations
    my_parser.add_argument('--i', action='store', type=str, required=True, help='input params path')
    my_parser.add_argument('--s', action='store', type=str, required=True, help='stage')
    my_parser.add_argument('--spath', action='store', type=str, required=True, help='stage path')
    my_parser.add_argument('--wkpath', action='store', type=str, required=True, help='working dir path')

    args = my_parser.parse_args()
    if args.solutionComb=="Clustering":
        params=ast.literal_eval(args.params) #{'n_clusters':4, 'init':'k-means++', 'max_iter':100, 'n_init':1}
        KMeansClustering.RunModel(args.modelGroup,args.modelType, args.dataType, args.subdataType, params, args.dataPath, args.writePath)
    #if args.solutionComb=="FreeEnergySim":
    #    params=ast.literal_eval(args.params) #{'n_clusters':4, 'init':'k-means++', 'max_iter':100, 'n_init':1}
    #    RunFreeEnergy(args.wkpath,args.i,args.spath, args.s)



    #compPath ="C:/Users/dunig/OneDrive/Documents/PharmaData/ChemicalData/KEGG/DataforPaper/compoundStructureKEGGdrugs3204673770244603068.txt" 
    #protPath ="C:/Users/dunig/OneDrive/Documents/PharmaData/ChemicalData/KEGG/DataforPaper/KEGG GENES DB/betaLactamasebr01553.pep.txt" 
    #modelType= "kmeans"
    ##dataType ="Compound" 
    ##subdataType="CompSmiles"
    #dataType ="Protein" 
    #subdataType="ProtSeq"
    #modelGroup="Clustering"
    ##subdataType ="IntStructProp" 
    #solutionComb ="KMeansCompStructProp"
    #writePath= 'C:/Users/dunig/Documents/BioPharmaResults'
    #params={'n_clusters':4, 'init':'k-means++', 'max_iter':100, 'n_init':1}
    #KMeansClustering.RunModel(modelGroup,modelType, dataType, subdataType, params, protPath, writePath)
    
    #wkpath='C:/Users/dunig/Documents/BioPharmaResults/BAT.py/BAT'
    #i='input.in'
    #s='Equilibrium,PrepareAfterEquil,AllPosesSystem,AnalysisStage'
    #spath="C:/Users/dunig/Documents/BioPharmaResults"
    #RunFreeEnergy(wkpath,i,spath, s)
    

if __name__ =="__main__":
    main()
