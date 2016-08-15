#!/usr/bin/env python

import sys, os, subprocess, inspect
import platform, multiprocessing
import string, re
from datetime import datetime, date, time
import copy
from argparse import ArgumentParser, FileType


"""
"""
def read_taxonomy_tree(tax_file):
    taxonomy_tree = {}
    for line in tax_file:
        fields = line.strip().split('\t')
        assert len(fields) == 5
        tax_id, parent_tax_id, rank = fields[0], fields[2], fields[4]
        assert tax_id not in taxonomy_tree
        taxonomy_tree[tax_id] = [parent_tax_id, rank]        
    return taxonomy_tree


"""
"""
def compare_scm(centrifuge_out, true_out, taxonomy_tree, rank):
    higher_ranked = {}
        
    ancestors = set()
    for tax_id in taxonomy_tree.keys():
        if tax_id in ancestors:
            continue
        while True:
            parent_tax_id, cur_rank = taxonomy_tree[tax_id]
            if parent_tax_id in ancestors:
                break
            if tax_id == parent_tax_id:
                break
            tax_id = parent_tax_id
            ancestors.add(tax_id)

    db_dic = {}
    first = True
    for line in open(centrifuge_out):
        if first:
            first = False
            continue
        read_name, seq_id, tax_id, score, _, _, _, _ = line.strip().split('\t')

        # Traverse up taxonomy tree to match the given rank parameter
        rank_tax_id = tax_id
        if rank != "strain":
            while True:
                if tax_id not in taxonomy_tree:
                    rank_tax_id = ""
                    break
                parent_tax_id, cur_rank = taxonomy_tree[tax_id]
                if cur_rank == rank:
                    rank_tax_id = tax_id
                    break
                if tax_id == parent_tax_id:
                    rank_tax_id = ""
                    break
                tax_id = parent_tax_id
        else:
            assert rank == "strain"
            if tax_id in ancestors:
                continue

        if rank_tax_id == "":
            # higher_ranked[read_name] = True            
            continue
        
        if read_name not in db_dic:
            db_dic[read_name] = set()
        db_dic[read_name].add(rank_tax_id)

    classified, unclassified, unique_classified = 0, 0, 0
    for line in open(true_out):
        if line.startswith('@'):
            continue

        fields = line.strip().split('\t')
        if len(fields) != 3:
            print >> sys.stderr, "Warning: %s missing" % (line.strip())
            continue
        read_name, tax_id = fields[1:3] 
        # Traverse up taxonomy tree to match the given rank parameter
        rank_tax_id = tax_id
        if rank != "strain":
            while True:
                if tax_id not in taxonomy_tree:
                    rank_tax_id = ""
                    break
                parent_tax_id, cur_rank = taxonomy_tree[tax_id]
                if cur_rank == rank:
                    rank_tax_id = tax_id
                    break
                if tax_id == parent_tax_id:
                    rank_tax_id = ""
                    break
                tax_id = parent_tax_id
        if rank_tax_id == "":
            continue
        if read_name not in db_dic:
            unclassified += 1
            continue

        maps = db_dic[read_name]
        if rank_tax_id in maps:
            classified += 1
            if len(maps) == 1 and read_name not in higher_ranked:
                unique_classified += 1
        else:
            unclassified += 1
            # daehwan - for debugging purposes
            # print read_name

    raw_unique_classified = 0
    for read_name, maps in db_dic.items():
        if len(maps) == 1 and read_name not in higher_ranked:
            raw_unique_classified += 1
    return classified, unique_classified, unclassified, len(db_dic), raw_unique_classified


"""
"""
def evaluate(index_base,
             ranks,
             verbose,
             debug):
    # Current script directory
    curr_script = os.path.realpath(inspect.getsourcefile(evaluate))
    path_base = os.path.dirname(curr_script) + "/.."

    def check_files(fnames):
        for fname in fnames:
            if not os.path.exists(fname):
                return False
        return True

    # Check if indexes exists, otherwise create indexes
    index_path = "%s/indexes/Centrifuge" % path_base
    # index_path = "."
    if not os.path.exists(path_base + "/indexes"):
        os.mkdir(path_base + "/indexes")
    if not os.path.exists(index_path):
        os.mkdir(index_path)
    index_fnames = ["%s/%s.%d.cf" % (index_path, index_base, i+1) for i in range(3)]
    assert check_files(index_fnames)

    # Read taxonomic IDs
    centrifuge_inspect = os.path.join(path_base, "../centrifuge-inspect")
    tax_ids = set()
    tax_cmd = [centrifuge_inspect,
               "--conversion-table",
               "%s/%s" % (index_path, index_base)]
    tax_proc = subprocess.Popen(tax_cmd, stdout=subprocess.PIPE)
    for line in tax_proc.stdout:
        _, tax_id = line.strip().split()
        tax_ids.add(tax_id)
    tax_ids = list(tax_ids)

    # Read taxonomic tree
    tax_tree_cmd = [centrifuge_inspect,
                    "--taxonomy-tree",
                    "%s/%s" % (index_path, index_base)]    
    tax_tree_proc = subprocess.Popen(tax_tree_cmd, stdout=subprocess.PIPE, stderr=open("/dev/null", 'w'))
    taxonomy_tree = read_taxonomy_tree(tax_tree_proc.stdout)

    compressed = (index_base.find("compressed") != -1) or (index_base == "centrifuge_Dec_Bonly")

    read_fname = "centrifuge_data/bacteria_sim10K/bacteria_sim10K.fa"
    scm_fname = "centrifuge_data/bacteria_sim10K/bacteria_sim10K.truth_species"
    read_fnames = [read_fname, scm_fname]

    program_bin_base = "%s/.." % path_base
    centrifuge_cmd = ["%s/centrifuge" % program_bin_base,
                      # "-k", "20",
                      # "--min-hitlen", "15",
                      "-f",
                      "-p", "1",
                      "%s/%s" % (index_path, index_base),
                      read_fname]

    if verbose:
        print >> sys.stderr, ' '.join(centrifuge_cmd)

    out_fname = "centrifuge.output"
    proc = subprocess.Popen(centrifuge_cmd, stdout=open(out_fname, "w"), stderr=subprocess.PIPE)
    proc.communicate()

    results = {"strain"  : [0, 0, 0],
               "species" : [0, 0, 0],
               "genus"   : [0, 0, 0],
               "family"  : [0, 0, 0],
               "order"   : [0, 0, 0],
               "class"   : [0, 0, 0],
               "phylum"  : [0, 0, 0]}
    for rank in ranks:
        if compressed and rank == "strain":
            continue

        classified, unique_classified, unclassified, raw_classified, raw_unique_classified = \
            compare_scm(out_fname, scm_fname, taxonomy_tree, rank)
        results[rank] = [classified, unique_classified, unclassified]
        num_cases = classified + unclassified
        # if rank == "strain":
        #    assert num_cases == num_fragment

        print >> sys.stderr, "\t\t%s" % rank
        print >> sys.stderr, "\t\t\tsensitivity: {:,} / {:,} ({:.2%})".format(classified, num_cases, float(classified) / num_cases)
        print >> sys.stderr, "\t\t\tprecision  : {:,} / {:,} ({:.2%})".format(classified, raw_classified, float(classified) / raw_classified)
        print >> sys.stderr, "\n\t\t\tfor uniquely classified "
        print >> sys.stderr, "\t\t\t\t\tsensitivity: {:,} / {:,} ({:.2%})".format(unique_classified, num_cases, float(unique_classified) / num_cases)
        print >> sys.stderr, "\t\t\t\t\tprecision  : {:,} / {:,} ({:.2%})".format(unique_classified, raw_unique_classified, float(unique_classified) / raw_unique_classified)

        # Calculate sum of squared residuals in abundance
        if rank == "strain":
            abundance_SSR = compare_abundance("centrifuge_report.tsv", truth_fname, taxonomy_tree, debug)
            print >> sys.stderr, "\t\t\tsum of squared residuals in abundance: {}".format(abundance_SSR)



if __name__ == "__main__":
    parser = ArgumentParser(
        description='Centrifuge evaluation on Mason simulated reads')
    parser.add_argument("--index-base",
                        type=str,
                        default="b_compressed",
                        help='Centrifuge index such as b_compressed, b+h+v, and centrifuge_Dec_Bonly (default: b_compressed)')
    rank_list_default = "strain,species,genus,family,order,class,phylum"
    parser.add_argument("--rank-list",
                        dest="ranks",
                        type=str,
                        default=rank_list_default,
                        help="A comma-separated list of ranks (default: %s)" % rank_list_default)
    parser.add_argument('-v', '--verbose',
                        dest='verbose',
                        action='store_true',
                        help='also print some statistics to stderr')
    parser.add_argument('--debug',
                        dest='debug',
                        action='store_true',
                        help='Debug')

    args = parser.parse_args()
    if not args.index_base:
        parser.print_help()
        exit(1)
    ranks = args.ranks.split(',')
    evaluate(args.index_base,
             ranks,
             args.verbose,
             args.debug)
