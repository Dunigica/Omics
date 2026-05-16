
from strkernel.gappy_kernel import gappypair_kernel as gk
from strkernel.gappy_trie import gappypair_kernel as gt

class StringKernelSeq(object):
    def GetGappyKernel(sequences,ko=1,to=0,go=1,type="simple"):
        if type=="simple":
            X=gk(sequences,k=1,t=0,g=1)
        if type=="trie":
            X=gt(sequences,k=1,t=0,g=1)
        return X