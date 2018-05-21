from Bio import SeqIO
import pandas as pd
from collections import defaultdict
import random,os
import numpy as np
from .utils import read_metadata, get_numerical_dates

comment_char = '#'

def read_vcf(compressed, input_file):
    import gzip
    opn = gzip.open if compressed else open

    with opn(input_file, mode='rt') as f: #'rt' necessary for gzip
        for line in f:
            if line[0:2] == "#C":
                header = line.strip().split('\t')
                seq_keep = header[header.index("FORMAT")+1:]
                all_seq = seq_keep.copy() #because we need 'seqs to remove' for VCF
                return seq_keep, all_seq


def write_vcf(compressed, input_file, output_file, dropped_samps):
    #Read in/write out according to file ending
    inCall = "--gzvcf" if compressed else "--vcf"
    outCall = "| gzip -c" if output_file.lower().endswith('.gz') else ""

    toDrop = " ".join(["--remove-indv "+s for s in dropped_samps])
    call = ["vcftools", toDrop, inCall, input_file, "--recode --stdout", outCall, ">", output_file]

    print("Filtering samples using VCFTools with the call:")
    print(" ".join(call))
    os.system(" ".join(call))
    os.remove('out.log') #remove vcftools log file



def run(args):
    '''
    filter and subsample a set of sequences into an analysis set
    '''
    #Set flags if VCF
    is_vcf = False
    is_compressed = False
    if any([args.sequences.lower().endswith(x) for x in ['.vcf', '.vcf.gz']]):
        is_vcf = True
        if args.sequences.lower().endswith('.gz'):
            is_compressed = True


    ####Read in files

    #If VCF, open and get sequence names
    if is_vcf:
        seq_keep, all_seq = read_vcf(is_compressed, args.sequences)

    #if Fasta, read in file to get sequence names and sequences
    else:
        seqs = {seq.id:seq for seq in SeqIO.parse(args.sequences, 'fasta')}
        seq_keep = list(seqs.keys())

    meta_dict, meta_columns = read_metadata(args.metadata)


    ####Filtering steps

    if args.exclude and os.path.isfile(args.exclude):
        with open(args.exclude, 'r') as ifile:
            to_exclude = set([line.strip() for line in ifile if line[0]!=comment_char])
        seq_keep = [s for s in seq_keep if s not in to_exclude]

    if (args.min_date or args.max_date) and 'date' in meta_columns:
        dates = get_numerical_dates(meta_dict, fmt="%Y-%m-%d")
        if args.min_date:
            seq_keep = [s for s in seq_keep if np.min(dates[s])>args.min_date]
        if args.max_date:
            seq_keep = [s for s in seq_keep if np.min(dates[s])<args.max_date]

    if args.cat and args.viruses_per_cat:
        vpc = args.viruses_per_cat
        seq_names_by_cat = defaultdict(list)

        for seq_name in seq_keep:
            cat = []
            if seq_name not in meta_dict:
                print("WARNING: no metadata for %s, skipping"%seq_name)
                continue
            else:
                m = meta_dict[seq_name]
            for c in args.cat:
                if c in m:
                    cat.append(m.loc[c])
                elif c in ['month', 'year'] and 'date' in m:
                    try:
                        year = int(m["date"].split('-')[0])
                    except:
                        print("WARNING: no valid year, skipping",seq_name, m["date"])
                        continue
                    if c=='month':
                        try:
                            month = int(m["date"].split('-')[1])
                        except:
                            month = random.randint(1,12)
                        cat.append((year, month))
                    else:
                        cat.append(year)
            seq_names_by_cat[tuple(cat)].append(seq_name)

        seq_subsample = []
        for cat, s in seq_names_by_cat.items():
            tmp_seqs = [seq_name for seq_name in s]
            seq_subsample.extend(tmp_seqs if len(s)<=vpc
                                 else random.sample(tmp_seqs,vpc))
    else:
        seq_subsample = seq_keep


    ####Write out files

    if is_vcf:
        #get the samples to be deleted, not to keep, for VCF
        dropped_samps = list(set(all_seq) - set(seq_subsample))
        write_vcf(is_compressed, args.sequences, args.output, dropped_samps)

    else:
        seq_to_keep = [seq for id,seq in seqs.items() if id in seq_subsample]
        SeqIO.write(seq_to_keep, args.output, 'fasta')


