import numpy as np
import pandas as pd
import sklearn
from sklearn.cluster import KMeans,AgglomerativeClustering,SpectralClustering
import pickle




class Model(object):        
    def ModelFactory(modeltype="kmeans",params={'n_clusters':4, 'init':'k-means++', 'max_iter':100, 'n_init':1}):
        Model={
            "kmeans":KMeans,
            "AgglomerativeCluster":AgglomerativeClustering,
            "SpectralClustering": SpectralClustering           
            }
        return Model[modeltype](**params)
