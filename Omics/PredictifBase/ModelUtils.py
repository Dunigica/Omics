import numpy as np

class ModelUtils:
   def read_data_to_list(path):
        data_file=open(path, 'r')
        data_list=data_file.readlines()
        return data_list
   

   def split_labels_given_symb(label, symb):
        array_label=label.split(symb)
        return array_label
