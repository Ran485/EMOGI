import networkx as nx
import numpy as np
import pandas as pd
import h5py, argparse, operator

def softmax(x):
    """Calculate softmax with numerical stability."""
    e_x = np.exp(x - np.max(x))
    return e_x / e_x.sum()

def load_diff_expr(file_name_up, file_name_down):
    """Loads differential up and down-regulated genes."""
    differential_expression_up = pd.read_html(file_name_up,
                                           index_col=2,
                                           header=0
                                          )[0]
    differential_expression_down = pd.read_html(file_name_down,
                                               index_col=2,
                                               header=0
                                               )[0]
    print ("Loaded Differential Expression from html...")

    # concatenate the up and down-regulated genes
    differential_expression_down.drop('Ensembl', inplace=True)
    differential_expression_down = differential_expression_down.convert_objects(convert_numeric=True)
    de = pd.concat([differential_expression_up, differential_expression_down])
    return de

def get_personalization_vec(diff_expr, gene_names):
    """Computes the personalization vector from differential expression data."""

    # add column with node numbers (as in the networkx graph) to the gene names
    indices = np.arange(0, gene_names.shape[0]).reshape(gene_names.shape[0], 1)
    gene_names_with_index = np.hstack([gene_names, indices])
    gene_names_df = pd.DataFrame(gene_names_with_index[:, 1:],
                                 index=gene_names_with_index[:, 0],
                                 columns=['Gene-name', 'Node-number']
                                )

    # join gene names and differential expression
    names_with_de = gene_names_df.join(diff_expr, lsuffix='_left')
    genes_zero_de = names_with_de.log2FoldChange.isnull().sum()
    print ("{} genes in network don't have any differential expression values (setting to zero)!".format(genes_zero_de))

    # calculate random walk probabilities from log2FoldChange
    names_with_de.ix[names_with_de.log2FoldChange.isnull(), 'log2FoldChange'] = 0
    names_with_de['rw_prob'] = softmax(abs(names_with_de.log2FoldChange))

    # construct dict which can be fed to the networkx pagerank algorithm
    personalization = {row['Node-number']:row.rw_prob for ens, row in names_with_de.iterrows()}
    return personalization


def pagerank(network, gene_names, diff_expr=None, alpha=0.3):
    """Execute PageRank/NetRank algorithm.

    This function calculates the PageRanks or NetRanks for the given PPI network
    and optional differential expression values.

    Parameters:
    ----------
    network_path:           Path to the network in hdf5 container (with gene names).
                            Gene names and expression data are assumed to be in
                            the same order as the nodes in the adjacency matrix.

    diff_expr:              Differential expression dataframe. If set to None,
                            PageRank is calculated, otherwise NetRank will be used.

    Returns:
    -------
    A list of tuples with the sorted PageRank/NetRank scores and gene names.
    """
    # build networkx graph
    G = nx.from_numpy_matrix(network)

    # compute personalization vector and do pagerank/netrank
    if not diff_expr is None:
        personalization = get_personalization_vec(diff_expr, gene_names)
        pagerank_vals = nx.pagerank(G,
                                    personalization=personalization,
                                    alpha=alpha
                                    )
    else:
        pagerank_vals = nx.pagerank(G)

    # some output statistics
    #maxi = max(pagerank_vals, key=pagerank_vals.get)
    #print ("Maximum Pagerank: Index: {}\tPagerank: {}".format(maxi, pagerank_vals[maxi]))
    #mini = min(pagerank_vals, key=pagerank_vals.get)
    #print ("Minimum Pagerank: Index: {}\tPagerank: {}".format(mini, pagerank_vals[mini]))

    # sort pagerank results (dict with gene idx and pagerank val)
    pagerank_sorted = sorted(pagerank_vals.items(), key=operator.itemgetter(1))[::-1]
    return pagerank_sorted, gene_names

def write_ranking(ranks_sorted, gene_names, out_path):
    with open(out_path, 'w') as res:
        count = 1
        res.write('Gene_ID\tGene_Name\tRank\tScore\n')
        for gene_idx, pr in ranks_sorted:
            res.write("{}\t{}\t{}\t{}\n".format(gene_names[gene_idx][0], gene_names[gene_idx][1], count, pr))
            count += 1

def parseArgs():
    parser = argparse.ArgumentParser(description='Execute PageRank/NetRank on PPI Network')
    parser.add_argument('--ppi', help='path to ppi network hdf5 container',
                        dest='ppi'
                        )
    parser.add_argument('--de',
                        help='differential expression file (csv)',
                        dest='de',
                        default=None,
                        type=str
                        )
    parser.add_argument('--alpha',
                        help='Restart probability in PageRank (importance of topology vs. DE)',
                        dest='alpha',
                        type=float
                        )
    parser.add_argument('--out',
                        help='Path to output file',
                        dest='out_path',
                        type=str
                        )
    args = parser.parse_args()
    return args.ppi, args.de, args.alpha, args.out_path

if __name__ == "__main__":
    ppi_path, de_path, alpha, out_path = parseArgs()

    # load DE (usually GFP+ vs. Control after 16 hours for up and down-regulated genes)
    # Unfortunately, we only have pvalue < .05, fill the rest with zeros.
    if not de_path is None:
        de = pd.DataFrame.from_csv(de_path).dropna()
    else:
        de = None

    # load network and gene names
    with h5py.File(ppi_path, 'r') as f:
        ppi_network = f['network'][:]
        gene_names = f['gene_names'][:]

    # execute PageRank/NetRank with PPI network and write results to file
    scores, gene_names = pagerank(ppi_network, gene_names, de, alpha)
    write_ranking(scores, gene_names, out_path)

    print ("Done with PageRank Algorithm! Exit!")
