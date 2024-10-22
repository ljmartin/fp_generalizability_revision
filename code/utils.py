import numpy as np
from scipy import sparse
from scipy.spatial.distance import pdist, cdist, squareform
import copy

from sklearn.metrics import precision_score, recall_score, roc_auc_score, label_ranking_loss
from sklearn.metrics import confusion_matrix, average_precision_score, label_ranking_average_precision_score
from sklearn.linear_model import LogisticRegression
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import StandardScaler

import matplotlib.pyplot as plt

def getSeed(seed=500):
    return seed

def getNames(short=False):
    if short:
        return ['morgan', 'cats', 'erg', 'rdk']
    else:
        return ['morgan', '2dpharm', 'atom_pair', 'erg', 'cats', 'layered', 'maccs', 'morgan_feat', 'pattern', 'rdk', 'topo_torsion']

def load_feature_and_label_matrices(type='morgan'):
    y = sparse.load_npz('./raw_data/y.npz').toarray()
    if type=='cats':
        x = sparse.load_npz('./processed_data/fingerprints/cats.npz').toarray()
        x = sparse.csr_matrix(StandardScaler().fit_transform(x))
    else:
        x = sparse.load_npz('./processed_data/fingerprints/'+type+'.npz')
    return x, y


def get_subset(x, y, indices):
    y_ = y[:,indices]
    #remove ligands that do not have a positive label in the subset
    row_mask = y_.sum(axis=1)>0
    y_ = y_[row_mask]
    x_ = x[row_mask]
    return x_, y_






def split_clusters(pos_labels, neg_labels, pos_test_fraction, neg_test_fraction, shuffle=True):
    if shuffle:
        #Shuffle so we can do random selection of clusters:
        np.random.shuffle(pos_labels)
        np.random.shuffle(neg_labels)
    #count number of clusters:
    num_pos_clusters = len(pos_labels)
    num_neg_clusters = len(neg_labels)
    
    #get test and train positives:
    test_pos_clusters = pos_labels[:max(1,round(num_pos_clusters*pos_test_fraction))]
    train_pos_clusters = pos_labels[max(1,round(num_pos_clusters*pos_test_fraction)):]

    if isinstance(neg_test_fraction, float):
        #get test and train negatives:
        test_neg_clusters = neg_labels[:int(num_neg_clusters*neg_test_fraction)]
        train_neg_clusters = neg_labels[int(num_neg_clusters*neg_test_fraction):]
    else:
        if sum(neg_test_fraction)>1:
            raise ValueError('Sum of test proportion and train proportion must be less than 1')
        test_neg_clusters = neg_labels[:round(num_neg_clusters*neg_test_fraction[0])]
        train_neg_clusters = neg_labels[-round(num_neg_clusters*neg_test_fraction[1]):]
            
    #combined:
    test_clusters = list(test_pos_clusters)+list(test_neg_clusters)
    train_clusters = list(train_pos_clusters)+list(train_neg_clusters)
    
    return test_clusters, train_clusters

def _split_indices(y_, idx, clusterer, test_clusters, train_clusters):
    alltest = np.isin(clusterer.labels_, test_clusters)
    alltrain = np.isin(clusterer.labels_, train_clusters)
    allpos = y_[:,idx].astype(bool)
    allneg = ~allpos
    return alltest, alltrain, allpos, allneg

def get_four_matrices(y_, idx, clusterer, test_clusters, train_clusters):
    alltest, alltrain, allpos, allneg = _split_indices(y_, idx, clusterer, test_clusters, train_clusters)
    actives_test_indices = (alltest&allpos).nonzero()[0]
    actives_train_indices = (alltrain&allpos).nonzero()[0]
    inactives_test_indices = (alltest&allneg).nonzero()[0]
    inactives_train_indices = (alltrain&allneg).nonzero()[0]
    return actives_test_indices, actives_train_indices, inactives_test_indices, inactives_train_indices

def calc_AVE_quick(dmat, actives_train, actives_test, inactives_train, inactives_test):
    inactive_dmat = dmat[inactives_test]
    iTest_iTrain_D = inactive_dmat[:,inactives_train].min(1)
    iTest_aTrain_D = inactive_dmat[:,actives_train].min(1)
    
    active_dmat = dmat[actives_test]
    aTest_aTrain_D = active_dmat[:,actives_train].min(1)
    aTest_iTrain_D = active_dmat[:,inactives_train].min(1)

    aTest_aTrain_S = np.mean( [ np.mean( aTest_aTrain_D < t ) for t in np.linspace( 0, 1.0, 50 ) ] )
    aTest_iTrain_S = np.mean( [ np.mean( aTest_iTrain_D < t ) for t in np.linspace( 0, 1.0, 50 ) ] )
    iTest_iTrain_S = np.mean( [ np.mean( iTest_iTrain_D < t ) for t in np.linspace( 0, 1.0, 50 ) ] )
    iTest_aTrain_S = np.mean( [ np.mean( iTest_aTrain_D < t ) for t in np.linspace( 0, 1.0, 50 ) ] )
    
    ave = aTest_aTrain_S-aTest_iTrain_S+iTest_iTrain_S-iTest_aTrain_S
    return ave


def trim(dmat, train_indices, test_indices, fraction_to_trim):
    num_to_trim = int(len(train_indices)*fraction_to_trim)
    new_indices = train_indices[dmat[:,train_indices].min(0).argsort()[num_to_trim:]]
    return new_indices


def evaluate_split(x, y, idx, pos_train, pos_test, neg_train, neg_test, auroc=False, ap=True, weight=None):
    all_train = np.concatenate([pos_train, neg_train])
    all_test = np.concatenate([pos_test, neg_test])
    x_train = x[all_train]
    x_test = x[all_test]
    y_train = y[all_train][:,idx]
    y_test = y[all_test][:,idx]
    
    clf = LogisticRegression(solver='lbfgs', max_iter=1000, class_weight=weight)
    clf.fit(x_train, y_train)
    probas = clf.predict_proba(x_test)[:,1]

    results = {}
    if auroc:
        score = roc_auc_score(y_test, probas)
        results['auroc']=score
    if ap:
        score = average_precision_score(y_test, probas)
        results['ap']=score
    return results





###############################
##--------------------------###
###############################











def merge_feature_matrices(matrices):
    """Merges four feature matrices into two matrices (test/train) for subsequent
    model fitting by sklearn. It also generates label matrices. 
    The matrices are 2-dimensional feature matrices, often called "X" in sklearn
    terminology, i.e. shape (N,F) where N is the number of instances and F is 
    the feature dimension. 
    
    Parameters:
    	matrices (list): four matrices of 2D numpy arrays. These are:
    	- x_actives_train: Positive instances for the training set
    	- x_actives_test: Positive instances for the test set
    	- x_inactives_train: Negative instances for the training set
    	- x_inactives_test: Negative instances for the test set

    Returns:
    	- x_train, y_train, x_test, y_test: feature and label matrices for 
    	an sklearn classifier i.e. clf.fit(x_train, y_train), or 
    	clf.score(x_test, y_test).
    """
    x_actives_train, x_actives_test, x_inactives_train, x_inactives_test = matrices

    x_train = np.vstack([x_actives_train, x_inactives_train]) #stack train instances together
    x_test = np.vstack([x_actives_test, x_inactives_test]) #stack test instance together
    #build 1D label array based on the sizes of the active/inactive train/test 
    y_train = np.zeros(len(x_train))
    y_train[:len(x_actives_train)]=1
    y_test = np.zeros(len(x_test))
    y_test[:len(x_actives_test)]=1    
    return x_train, x_test, y_train, y_test

def split_feature_matrices(x_train, x_test, y_train, y_test, idx):
    """Does the opposite of merge_feature_matrices i.e. when given the 
    train and test matrices for features and labels, splits them into 
    train/active, test/active, train/inactive, test/inactive.

    Parameters:
    	- x_train, x_test, y_train, y_test (2D np.arrays): Feature 
        matrices and label matrices in the sklearn 'X' and 'Y' style.
        - idx (int): a column of the label matrix corresponding to the 
        protein target you wish to test. """
    x_actives_train = x_train[y_train[:,idx]==1]
    x_actives_test = x_test[y_test[:,idx]==1]
    
    x_inactives_train = x_train[y_train[:,idx]!=1]
    x_inactives_test = x_test[y_test[:,idx]!=1]
    
    return x_actives_train, x_actives_test, x_inactives_train, x_inactives_test


##The following performs test/train splitting by single-linkage clustering:
def get_split_indices(y_, idx, clusterer, test_clusters, train_clusters):
    alltest = np.isin(clusterer.labels_, test_clusters)
    alltrain = np.isin(clusterer.labels_, train_clusters)
    allpos = y_[:,idx].astype(bool)
    allneg = ~allpos
    return alltest, alltrain, allpos, allneg

def make_cluster_split(x_, y_, clust, percentage_holdout=0.2, test_clusters=False):
    """Given a X,Y, and a fitted clusterer from sklearn, this selects
    a percentage of clusters as holdout clusters, then constructs the X,Y matrices

    Parameters:
    	x_ (2d np.array): Feature matrix X
        y_ (2d np.array): Label matrix Y
        percentage_hold_out (float): Percentage of ligands desired as hold-out data.

    Returns:
    	x_train, x_test, y_train, y_test: feature and label matrices
        for an sklearn classifier. If this is confusing, see sklearn's 
        train_test_split function."""
    if isinstance(test_clusters, bool):
        test_clusters = np.random.choice(clust.labels_.max(), int(clust.labels_.max()*percentage_holdout), replace=False)
    mask = ~np.isin(clust.labels_, test_clusters)
    x_test = x_[~mask]
    x_train = x_[mask]
    y_test = y_[~mask]
    y_train = y_[mask]
    return x_train, x_test, y_train, y_test

##The following is to calculate AVE bias:
def fast_jaccard(X, Y=None):
    """credit: https://stackoverflow.com/questions/32805916/compute-jaccard-distances-on-sparse-matrix"""
    if isinstance(X, np.ndarray):
        X = sparse.csr_matrix(X)
    if Y is None:
        Y = X
    else:
        if isinstance(Y, np.ndarray):
            Y = sparse.csr_matrix(Y)
    assert X.shape[1] == Y.shape[1]

    X = X.astype(bool).astype(int)
    Y = Y.astype(bool).astype(int)
    intersect = X.dot(Y.T)
    x_sum = X.sum(axis=1).A1
    y_sum = Y.sum(axis=1).A1
    xx, yy = np.meshgrid(x_sum, y_sum)
    union = ((xx + yy).T - intersect)
    return (1 - intersect / union).A

def fast_dice(X, Y=None):
    if isinstance(X, np.ndarray):
        X = sparse.csr_matrix(X).astype(bool).astype(int)
    if Y is None:
        Y = X
    else:
        if isinstance(Y, np.ndarray):
            Y = sparse.csr_matrix(Y).astype(bool).astype(int)
            
    intersect = X.dot(Y.T)
    #cardinality = X.sum(1).A
    cardinality_X = X.getnnz(1)[:,None] #slightly faster on large matrices - 13s vs 16s for 12k x 12k
    cardinality_Y = Y.getnnz(1) #slightly faster on large matrices - 13s vs 16s for 12k x 12k
    return (1-(2*intersect) / (cardinality_X+cardinality_Y.T)).A

def calcDistMat( fp1, fp2, metric='jaccard' ):
    """Calculates the pairwise distance matrix between features
    fp1 and fp2"""
    return cdist(fp1, fp2, metric=metric)



def calc_distance_matrices(matrices, metric='dice'):
    """Performs the first step in calculating AVE bias: 
    calculating distance matrix between each pair of ligand sets. 
    
    Parameters:
    	matrices (list): set of four feature matrices in the order:
        x_actives_train, x_actives_test, x_inactives_train, x_inactives_test

    Returns:
    	distances (list): set of four distance matrices. Columns will
        be equal to the number of test set ligands, rows will be equal to 
        the number of train set ligands. """

    x_actives_train, x_actives_test, x_inactives_train, x_inactives_test = matrices
    #original method (slow - do not use):
    #aTest_aTrain_D = calcDistMat( x_actives_test, x_actives_train, metric )
    #aTest_iTrain_D = calcDistMat( x_actives_test, x_inactives_train, metric )
    #iTest_iTrain_D = calcDistMat( x_inactives_test, x_inactives_train, metric )
    #iTest_aTrain_D = calcDistMat( x_inactives_test, x_actives_train, metric )

    if metric=='jaccard':
        distFun = fast_jaccard
    if metric=='dice':
        distFun = fast_dice

    if x_inactives_train.shape[0]>15000:
        if isinstance(x_actives_test, sparse.csr_matrix):
            x_actives_test = x_actives_test.toarray()
        if isinstance(x_actives_train, sparse.csr_matrix):
            x_actives_train = x_actives_train.toarray()
        if isinstance(x_inactives_test, sparse.csr_matrix):
            x_inactives_test = x_inactives_test.toarray()
        if isinstance(x_inactives_train, sparse.csr_matrix):
            x_inactives_train = x_inactives_train.toarray()

        print(type(x_actives_test), type(x_actives_train), type(x_inactives_test), type(x_inactives_train))
        print('building actives train_index', x_actives_train.shape[0])
        x_actives_train_index = NNDescent(x_actives_train, metric='jaccard')
        print('building inactives train index', x_inactives_train.shape[0])
        x_inactives_train_index = NNDescent(x_inactives_train, metric='jaccard')
        print('querying actives train with actives test', x_actives_test.shape[0], x_actives_train.shape[0])
        _, aTest_aTrain_D = x_actives_train_index.query(x_actives_test)
        print('querying inactives train with actives test', x_actives_test.shape[0], x_inactives_train.shape[0])
        _, aTest_iTrain_D = x_inactives_train_index.query(x_actives_test)
        print('querying inactives train with inactives test', x_inactives_test.shape[0], x_inactives_train.shape[0])
        _, iTest_iTrain_D = x_inactives_train_index.query(x_inactives_test)
        print('querying actives train with inactives test', x_actives_test.shape[0], x_inactives_train.shape[0])
        _, iTest_aTrain_D = x_actives_train_index.query(x_inactives_test)

    else:
        #faster using sparse input data to avoid calculating lots of zeroes:
        aTest_aTrain_D = distFun(x_actives_test, x_actives_train)
        aTest_iTrain_D = distFun(x_actives_test, x_inactives_train)
        iTest_iTrain_D = distFun(x_inactives_test, x_inactives_train)
        iTest_aTrain_D = distFun(x_inactives_test, x_actives_train)
    return aTest_aTrain_D, aTest_iTrain_D, iTest_iTrain_D, iTest_aTrain_D
    
def calc_AVE(distances):
    """Calculates the AVE bias. Please see Wallach et.al https://doi.org/10.1021/acs.jcim.7b00403

    Parameters:
	distances (list): list of distances matrices returned by 
        `calc_distance_matrices()`
        
    Returns:
    	AVE (float): the AVE bias"""

    aTest_aTrain_D, aTest_iTrain_D, iTest_iTrain_D, iTest_aTrain_D = distances
    
    aTest_aTrain_S = np.mean( [ np.mean( np.any( aTest_aTrain_D < t, axis=1 ) ) for t in np.linspace( 0, 1.0, 50 ) ] )
    aTest_iTrain_S = np.mean( [ np.mean( np.any( aTest_iTrain_D < t, axis=1 ) ) for t in np.linspace( 0, 1.0, 50 ) ] )
    iTest_iTrain_S = np.mean( [ np.mean( np.any( iTest_iTrain_D < t, axis=1 ) ) for t in np.linspace( 0, 1.0, 50 ) ] )
    iTest_aTrain_S = np.mean( [ np.mean( np.any( iTest_aTrain_D < t, axis=1 ) ) for t in np.linspace( 0, 1.0, 50 ) ] )
    
    AVE = aTest_aTrain_S-aTest_iTrain_S+iTest_iTrain_S-iTest_aTrain_S
    return AVE

def calc_VE(distances):
    """Calculate the VE bias score. Please see Davis et. al at DOI 2001.03207 
    pre-print is available at: https://arxiv.org/abs/2001.03207 

    Parameters:
        distances (list): list of distances matrices returned by
        `calc_distance_matrices()`

    Returns:
        VE: the VE bias"""
    
    aTest_aTrain_D, aTest_iTrain_D, iTest_iTrain_D, iTest_aTrain_D = distances
    term_one = np.mean(aTest_iTrain_D.min(axis=1) - aTest_aTrain_D.min(axis=1))
    term_two = np.mean(iTest_aTrain_D.min(axis=1) - iTest_iTrain_D.min(axis=1))
    VE = np.sqrt(term_one**2+term_two**2)
    return VE


##For plotting in a particular style: 
##Please see https://github.com/ColCarroll/minimc for the source of inspiration
ALPHA = 0.7
def plot_fig_label(ax, lab):
    ax.text(-0.1, 1.15, lab, transform=ax.transAxes,
        fontsize=24, fontweight='bold', va='top', ha='right')

def set_mpl_params():
    plt.rcParams.update(
        {
            "axes.prop_cycle": plt.cycler(
                "color",
                [
                    "#1b6989",
                    "#e69f00",
                    "#009e73",
                    "#f0e442",
                    "#50b4e9",
                    "#d55e00",
                    "#cc79a7",
                    "#000000",
                ],
            ),
            "scatter.edgecolors": 'k',
            "grid.linestyle": '--',
            "font.serif": [
                "Palatino",
                "Palatino Linotype",
                "Palatino LT STD",
                "Book Antiqua",
                "Georgia",
                "DejaVu Serif",
                ],
            "font.family": "serif",
            "figure.facecolor": "#fffff8",
            "axes.facecolor": "#fffff8",
            "axes.axisbelow": True,
            "figure.constrained_layout.use": True,
            "font.size": 14.0,
            "hist.bins": "auto",
            "lines.linewidth": 3.0,
            "lines.markeredgewidth": 2.0,
            "lines.markerfacecolor": "none",
            "lines.markersize": 8.0,
        }

    )
