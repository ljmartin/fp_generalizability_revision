from rdkit import Chem
from rdkit.Chem import AllChem, Draw
from rdkit.Chem.Draw import IPythonConsole
import numpy as np
import itertools
import matplotlib.pyplot as plt

import pandas as pd
from tqdm import tqdm
from scipy import sparse




def makeMols(num=None):
    smiles = pd.read_csv('./raw_data/allSmiles.csv', header=None)
    mols = list()
    for smile in smiles[0].iloc[0:num]:
        mols.append(Chem.MolFromSmiles(smile))
    return np.array(mols)

#D
hbd = '[$([N;!H0;v3,v4&+1]),$([O,S;H1;+0]),n&H1&+0]'
#A
hba = '[$([O,S;H1;v2;!$(*-*=[O,N,P,S])]),$([O,S;H0;v2]),$([O,S;-]),$([N;v3;!$(N-*=[O,N,P,S])]),n&H0&+0,$([o,s;+0;!$([o,s]:n);!$([o,s]:c:n)])]'
#E (old aromatic):
pi_e = '[c,$(C=C-*),$(C#C)]'
#H
halogen = '[F,Cl,Br,I]'
#B
basic ='[#7;+,$([N;H2&+0][$([C,a]);!$([C,a](=O))]),$([N;H1&+0]([$([C,a]);!$([C,a](=O))])[$([C,a]);!$([C,a](=O))]),$([N;H0&+0]([C;!$(C(=O))])([C;!$(C(=O))])[C;!$(C(=O))])]'
#P
acidic = '[$([C,S](=[O,S,P])-[O;H1,-1])]'
#L
aliphatic_C = '[!$(C=C-*);!$(C#*);$(C-*)]'


from collections import OrderedDict
atomTypes = ['D', 'A', 'E', 'H', 'B', 'P', 'L']
possible_pairs = [sorted(i)[0]+sorted(i)[1] for i in itertools.combinations_with_replacement(atomTypes, 2)]

def setProps(mol):
    for label, pphore in zip(atomTypes, [hbd, hba, pi_e, halogen, basic, acidic, aliphatic_C]):
        atoms = [i[0] for i in mol.GetSubstructMatches(Chem.MolFromSmarts(pphore))]
        for atom in atoms:
            mol.GetAtomWithIdx(atom).SetProp(label, str(1))

def addBond(point, mol, distance, fp):
    atom1 = [i for i, value in mol.GetAtomWithIdx(point[0]).GetPropsAsDict().items() 
             if i in atomTypes]
    atom2 = [i for i, value in mol.GetAtomWithIdx(point[1]).GetPropsAsDict().items() 
             if i in atomTypes]
    for x in atom1:
        for y in atom2:
            key = sorted((x,y))[0]+sorted((x,y))[1]
            fp[key][distance] = fp[key][distance]+1

def make_blank_distributions():
    mol_fp = OrderedDict()
    for pair in possible_pairs:
        arr = np.array([0,0,0,0,0,0,0,0,0,0])
        mol_fp[pair] = arr
    return mol_fp

def getDistances(mol, fp_dict):
    distanceMatrix = Chem.GetDistanceMatrix(mol)
    for point in itertools.combinations(range(distanceMatrix.shape[0]), 2):
        distance = distanceMatrix[point[0]][point[1]]
        if distance<11:
            addBond(point, mol, int(distance)-1, fp_dict)
            #addBond_gaussian(point, mol, int(distance)-1, fp_dict)
    return fp_dict


def addBond_gaussian(point, mol, distance, fp):
    atom1 = [i for i, value in mol.GetAtomWithIdx(point[0]).GetPropsAsDict().items() 
             if i in atomTypes]
    atom2 = [i for i, value in mol.GetAtomWithIdx(point[1]).GetPropsAsDict().items() 
             if i in atomTypes]
    for x in atom1:
        for y in atom2:
            key = sorted((x,y))[0]+sorted((x,y))[1]
            g_dist = np.abs(np.arange(0, 10, 1) - distance)
            g_dist = np.exp(-g_dist*g_dist)
            fp[key] = fp[key]+ g_dist
            
            
def make_FP(mol):
    setProps(mol)
    fp_dict = make_blank_distributions()
    fp_dict = getDistances(mol, fp_dict)
    blank_FP = np.zeros([28,10])
    for count, (key, value) in enumerate(fp_dict.items()):
        blank_FP[count] = value
    return blank_FP.reshape(1,-1)[0]


if __name__=='__main__':

    mols = makeMols()
    
    fps = list()
    for mol in tqdm(mols):
        fp = make_FP(mol)
        fps.append(fp)

    fps = np.array(fps)
    sparse.save_npz('./processed_data/fingerprints/cats.npz', sparse.csr_matrix(fps))
