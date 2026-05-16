import numpy as np
import pandas as pd
import sklearn
from sklearn.cluster import KMeans,AgglomerativeClustering,SpectralClustering
from PredictifBase.ModelFactory import Model
from LoadFromFile.LoaderFactory import Loader
import pickle
from PredictifBase.StringKernelSeq import StringKernelSeq

class RunModel(object):
    def __init__(self,modelgroup,modeltype,datatype,subdatatype,params,data_path,write_path):
        self.modelgroup=modelgroup
        self.modeltype=modeltype
        self.datatype=datatype
        self.subdatatype=subdatatype
        self.params=params #params={'n_clusters':4, 'init':'k-means++', 'max_iter':100, 'n_init':1}
        self.data_path=data_path
        self.write_path=write_path
        self.y=list()
         
        self.LoadData(self.datatype,self.subdatatype,self.data_path)
        self.FitPredictModel
        
        
    
        
    


    @classmethod
    def LoadData(self,data_type,subdatatype,data_path):
        spec_loader=Loader.LoaderFactory(datatype=data_type)
        rawX=spec_loader.Load(data_path)
        self.X=[] 
        if subdatatype=="IntStructProp":                     
            x_o_dic=dict((a,vars(rawX[0].compoundStructure.compoundStructuralProperties)[a]) for a in vars(rawX[0].compoundStructure.compoundStructuralProperties).keys() if not a.startswith('__') and not callable(getattr(rawX[0].compoundStructure.compoundStructuralProperties, a)))  
            keys=[key for key in x_o_dic.keys()   if self.isfloat(x_o_dic[key])==True]             
            for elem in rawX:
                dict_var=dict((a,vars(elem.compoundStructure.compoundStructuralProperties)[a]) for a in vars(elem.compoundStructure.compoundStructuralProperties).keys() if not a.startswith('__') and not callable(getattr(elem.compoundStructure.compoundStructuralProperties, a)))           
                compStruct=[float(dict_var[key]) for key in keys ]                
                self.X.append(np.array(compStruct))
                self.ids=[elem.compoundStructure.cid for elem in rawX]
            self.X=np.array(self.X)
        if subdatatype=="CompSmiles":            
            smiles=[elem.compoundStructure.compoundStructuralProperties.PUBCHEM_OPENEYE_CAN_SMILES for elem in rawX]                
            smiles_arr=np.array([np.array(smile) for smile in smiles])
            self.ids=[elem.compoundStructure.cid for elem in rawX]
            simple_kernel=StringKernelSeq.GetGappyKernel(sequences=smiles_arr,ko=1,to=0,go=1,type="simple")
            simple_kernel_transp=simple_kernel.transpose()
            self.X=simple_kernel.dot(simple_kernel_transp)
        if subdatatype=="ProtSeq": 
            pseqs=[elem.AASequence for elem in rawX]                
            pseq_arr=np.array([np.array(pseq) for pseq in pseqs])
            self.ids=[elem.ProteinName for elem in rawX]
            simple_kernel=StringKernelSeq.GetGappyKernel(sequences=pseq_arr,ko=1,to=0,go=1,type="simple")
            simple_kernel_transp=simple_kernel.transpose()
            self.X=simple_kernel.dot(simple_kernel_transp)        
        print(self.X.shape)  #...x15
            




    @property
    def FitPredictModel(self):
        ml_model=Model.ModelFactory(modeltype=self.modeltype,params=self.params)
        if self.modelgroup=="Clustering":
            ml_model.fit(self.X)
            results=ml_model.labels_
        if self.modelgroup=="Classification": #not implemented yet
            ml_model.fit(self.X,self.y)            
            results=ml_model.predict(self.X)    
        self.SaveResultsToFile(self.write_path,results,self.ids,self.modeltype,self.datatype,self.subdatatype)
        self.SaveModelToFile(ml_model,self.write_path,self.modeltype,self.datatype,self.subdatatype)


    @classmethod
    def SaveResultsToFile(self,sv_path,item,ids,modeltype,datatype,subdatatype):
        header="Prediction Results" + str( modeltype)+"_"+ str(datatype) + "\n"
        result_format=pd.DataFrame().assign(id=ids).assign(pred=item)
        w_path=sv_path+"/ClusterAndProfilingOutputs/"+str( modeltype)+"_"+ str(datatype)+"_"+ str(subdatatype)+"_prediction.txt"
        with open(w_path,"w") as tf:
            tf.write(header)
        tf.close()
        result_format.to_csv(w_path,header=None,index=None,sep=",", mode="a")
        

    @classmethod
    def SaveModelToFile(self,model,write_path,modeltype,datatype,subdatatype):
        m_path=write_path+"/models/"+str( modeltype)+"_"+ str(datatype)+"_"+ str(subdatatype)+"_model.txt"
        pickle.dump(model, open(m_path, 'wb'))
        

    @classmethod
    def isfloat(self,value):
        try:
            float(value)
            return True
        except ValueError:
            return False

