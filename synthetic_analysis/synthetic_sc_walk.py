import numpy as np
import networkx as nx
from scipy.spatial import Delaunay

import os


### Generate graph + walks ###
def random_SC_graph(n):
    """
    Randomly generates a graph of simplicial complexes, made up of n nodes.
    Graph has holes in top left and bottom right regions.

    :param n: # of nodes in graph

    Returns:
        NetworkX DiGraph object G
        Sorted list of nodes V
        Sorted list of edges E
        Map  (edge tuples -> indices in E) E_lookup
        List of faces
        List of valid node indexes (nodes not in either hole)

    """

    points = np.random.rand(n,2)
    tri = Delaunay(points)

    valid_idxs = np.where((np.linalg.norm(points - [1/4, 3/4], axis=1) > 1/8) \
                          & (np.linalg.norm(points - [3/4, 1/4], axis=1) > 1/8))[0]

    faces = [t for t in tri.simplices if np.in1d(t,valid_idxs).all()]

    # SC matrix construction
    G = nx.DiGraph()
    G.add_nodes_from(np.arange(n)) # add nodes that are excluded to keep indexing easy

    for f in faces:
        [a,b,c] = sorted(f)
        G.add_edge(a,b)
        G.add_edge(b,c)
        G.add_edge(a,c)
    
    V = sorted(G.nodes)
    E = sorted(G.edges)
    E_lookup = dict(zip(E,range(len(E))))

    return G, V, E, E_lookup, faces, points, valid_idxs

def incidience_matrices(G, V, E, faces):
    """
    Returns incidence matrices B1 and B2

    :param G: NetworkX DiGraph
    :param V: list of nodes
    :param E: list of edges
    :param faces: list of faces in G

    Returns B1 (|V| x |E|) and B2 (|E| x |faces|)
    """
    B1 = np.array(nx.incidence_matrix(G, nodelist=V, edgelist=E, oriented=True).todense())
    B2 = np.zeros([len(E),len(faces)])


    for e_idx, e in enumerate(E):
        [e0,e1] = sorted(e)
        for f_idx, f in enumerate(faces):
            if np.in1d(e,f).all():
                [a,b,c] = sorted(f)
                if e0==a:
                    if e1==b:
                        B2[e_idx, f_idx] = 1
                    else:
                        B2[e_idx, f_idx] = -1
                else:
                    B2[e_idx, f_idx] = 1
    return B1, B2

def generate_random_walks(G, points, valid_idxs, E, E_lookup, m=1000):
    """
    Generates m random walks over the valid nodes in G.

    trajectories will look like one of the following:
        BEGIN -> A0 -> B0 -> END (top left regions)
        BEGIN -> A1 -> B1 -> END (middle regions)
        BEGIN -> A2 -> B2 -> END (bottom right regions

    :param G: NetworkX digraph
    :param points: list of (x, y) points that make up the graph's nodes
    :param valid_idxs: list of valid node indexes in
    :param E: sorted list of edges in E
    :param E_lookup: map (edge tuple -> index
    :param m: # of walks to generate

    Returns:
        paths: List of walks (each walk is a list of nodes)
        flows: E x m matrix:
            index i,j is 1 if flow j contains edge e in the direction of increasing node #
            i,j is -1 if decreasing node #
            else 0
    """
    points_valid = points[valid_idxs]

    # "partition" node space
    BEGIN = valid_idxs[np.sum(points_valid, axis=1) < 1/4]
    END = valid_idxs[np.sum(points_valid, axis=1) > 7/4]

    A012 = valid_idxs[(np.sum(points_valid, axis=1) > 1/4) & (np.sum(points_valid, axis=1) < 1)]
    A0 = A012[(points[A012,1]-points[A012,0] < 1/2) & (points[A012,1]-points[A012,0] > -1/2)]
    A1 = A012[points[A012,1]-points[A012,0] > 1/2]
    A2 = A012[points[A012,1]-points[A012,0] < -1/2]

    B012 = valid_idxs[(np.sum(points_valid, axis=1) < 7/4) & (np.sum(points_valid, axis=1) > 1)]
    B0 = B012[(points[B012,1]-points[B012,0] < 1/2) & (points[B012,1]-points[B012,0] > -1/2)]
    B1_ = B012[points[B012,1]-points[B012,0] > 1/2]
    B2_ = B012[points[B012,1]-points[B012,0] < -1/2]



    paths = []
    G_undir = G.to_undirected()



    for i in range(m):
        v_begin = np.random.choice(BEGIN)
        if i%3==0:
            v_1 = np.random.choice(A0)
            v_2 = np.random.choice(B0)
        elif i%3==1:
            v_1 = np.random.choice(A1)
            v_2 = np.random.choice(B1_)
        else:
            v_1 = np.random.choice(A2)
            v_2 = np.random.choice(B2_)
        v_end = np.random.choice(END)

        path = nx.shortest_path(G_undir, v_begin, v_1)[:-1] + \
            nx.shortest_path(G_undir, v_1, v_2)[:-1] + \
            nx.shortest_path(G_undir, v_2, v_end)

        paths.append(path)

    # flows = np.zeros([len(E),m])
    #
    # for i,path in enumerate(paths):
    #     l = len(path)
    #     for j in range(l-1):
    #         v0 = path[j]
    #         v1 = path[j+1]
    #         if v0 < v1:
    #             k = E_lookup[(v0,v1)]
    #             flows[k,i] += 1
    #         else:
    #             k = E_lookup[(v1,v0)]
    #             flows[k,i] -= 1

    return paths

def synthesize_SC_graph(n, m):
    """
    Generates a random n-node SC graph with holes in it.
    """

    G, V, E, E_lookup, faces, points, valid_idxs = random_SC_graph(n)
    B1, B2 = incidience_matrices(G, V, E, faces)

    return G, E, E_lookup, B1, B2, points, valid_idxs


### Format as training data for walk prediction ###

# given a path, return the flow vector
# assumes edges (a,b) obey a<b
def path_to_flow(path, E_lookup, m):
    '''
    path: list of nodes
    E_lookup: dictionary mapping edge tuples to indices
    m: number of edges
    '''
    l = len(path)
    f = np.zeros([m,1])
    for j in range(l-1):
        v0 = path[j]
        v1 = path[j+1]
        if v0 < v1:
            k = E_lookup[(v0,v1)]
            f[k] += 1
        else:
            k = E_lookup[(v1,v0)]
            f[k] -= 1
    return f

# given a node, return an array of neighbors
def neighborhood(G, v):
    '''
    G: networkx undirected graph
    v: node label
    '''
    return np.array(G[v])

# given an array of nodes and a correct node, return an indicator vector
def neighborhood_to_onehot(Nv, w, D):
    '''
    Nv: numpy array
    w: integer, presumably present in Nv
    D: max degree, for zero padding
    '''
    onehot = (Nv==w).astype(np.float)
    onehot_final = np.zeros(D)
    onehot_final[:onehot.shape[0]] = onehot
    return np.array([onehot_final]).T

# given an array of neighbors, return the subincidence matrix
def conditional_incidence_matrix(B1, Nv, D):
    '''
    B1: numpy array
    Nv: row indices of B1 to extract
    D: max degree, for zero padding
    '''
    Bcond = np.zeros([D,B1.shape[1]])
    Bcond[:len(Nv),:] = B1[Nv]
    return Bcond

def multi_hop_neighborhood(G, v, h):
    """
    Returns the h-hop neighborhood of node v in graph G
    """
    if h == 1:
        return set(G[v])
    Nv = set([])
    for nbr in G[v]:
        Nv.update(multi_hop_neighborhood(G, nbr, h - 1))
    return Nv

### v   Entry points   v ###
def generate_training_data(n, m, hops=(1,)):
    """
    Generates an m-walk synthetic training data over an n-node SC graph. Returns a flows_in, Bconds, and targets
        as lists of matrices to account for generating datasets with multiple numbers of hops.
    """

    G, E, E_lookup, B1, B2, points, valid_idxs = synthesize_SC_graph(n, m)
    G_undir = G.to_undirected()

    paths = generate_random_walks(G, points, valid_idxs, E, E_lookup, m=m)

    # get max one-hop degree for padding
    D_1hop = np.max(list(dict(G_undir.degree()).values()))

    flows_ins = []
    Bcondss = []
    targetss = []


    # truncate paths (length between 4 and (4 + max(hops))

    paths_truncated = [p[:4 + np.random.choice(len(p) - 4 + (max(hops) - 1))] for p in paths]
    prefixes = [p[:-max(hops)] for p in paths_truncated]
    suffixes_with_last_pref = [p[-(max(hops) + 1):] for p in paths_truncated]

    last_nodes = [s[0] for s in suffixes_with_last_pref]

    # generate flows_in and targets for 1-hop, 2-hop, and 3-hop prediction
    for h in hops:

        # paths
        # convert to flow
        flows_in = [path_to_flow(p, E_lookup, len(E)) for p in prefixes]


        # get conditional incidence matrices
        penultimate_nbrs = [np.array(sorted(neighborhood(G_undir, s[h - 1]))) for s in suffixes_with_last_pref]
        endpoints = [s[h] for s in suffixes_with_last_pref]

        # print('Mean number of choices: {}'.format(np.mean([len(Nv) for Nv in paths_truncated_multihop_neighbors])))
        Bconds = [conditional_incidence_matrix(B1, Nv, D_1hop) for Nv in penultimate_nbrs]
        # get max multi-hop degree for padding
        # create one-hot target vectors
        targets = [neighborhood_to_onehot(Nv, w, D_1hop) for Nv, w in zip(penultimate_nbrs, endpoints)]

        # final matrices
        flows_ins.append(np.array(flows_in))
        Bcondss.append(np.array(Bconds))
        targetss.append(np.array(targets))

    # train & test masks
    train_mask = np.asarray([1] * int(flows_ins[0].shape[0] * 0.8) + [0] * int(flows_ins[0].shape[0] * 0.2))
    np.random.shuffle(train_mask)
    test_mask = 1 - train_mask


    return flows_ins, [B1, B2, Bcondss], targetss, train_mask, test_mask, G_undir, last_nodes

def save_training_data(flows_in, B1, B2, Bconds, targets, train_mask, test_mask, G_undir, last_nodes, folder):
    """
    Saves training dataset to folder
    """
    if not os.path.isdir(folder):
        os.mkdir(folder)

    file_paths = [os.path.join(folder, ar + '.npy') for ar in ('flows_in', 'B1', 'B2', 'Bconds', 'targets', 'train_mask',
                                                               'test_mask', 'G_undir', 'last_nodes')]

    np.save(file_paths[0], flows_in)
    np.save(file_paths[1], B1)
    np.save(file_paths[2], B2)
    np.save(file_paths[3], Bconds)
    np.save(file_paths[4], targets)
    np.save(file_paths[5], train_mask)
    np.save(file_paths[6], test_mask)
    nx.readwrite.write_adjlist(G_undir, file_paths[7])
    np.save(file_paths[8], last_nodes)


def load_training_data(folder):
    """
    Loads training data from trajectory_data folder
    """
    file_paths = [os.path.join(folder, ar + '.npy') for ar in ('flows_in', 'B1', 'B2', 'Bconds', 'targets', 'train_mask',
                                                               'test_mask', 'G_undir', 'last_nodes')]
    G_undir = nx.readwrite.read_adjlist(file_paths[7])
    remap = {node: int(node) for node in G_undir.nodes}
    G_undir = nx.relabel_nodes(G_undir, remap)

    return np.load(file_paths[0]), [np.load(p) for p in file_paths[1:4]], np.load(file_paths[4]), \
           np.load(file_paths[5]), np.load(file_paths[6]), G_undir, np.load(file_paths[8])


