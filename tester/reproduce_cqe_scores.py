from cbtest_wrapper import test_sample, test_sample_refpatch
import cPickle
from collections import OrderedDict
import csv
import glob
import os

#### Settings for this script ####
SCORE_TO_COMPARE = 'PerfScore'
#SCORE_TO_COMPARE = 'ExecTimeOverhead'
ALLOW_RECOMPUTING = False


# Too big to put all into this git, and used just for internal testing anyway:
# https://github.com/CyberGrandChallenge/samples/tree/master/cqe-challenges
SRC_DIR = './cqe-recap/source'
# http://repo.cybergrandchallenge.com/cqe_results/cqe_final_submissions.zip
SUBMISSIONS_DIR = './cqe-recap/submissions'
# http://repo.cybergrandchallenge.com/cqe_results/cqe_results-0d5587e0.zip
SCORES_CSV='./cqe-recap/results/CQE_SCORES.csv'


def compute_reference_scores(cset_name):
    sample_dir = SRC_DIR+'/'+cset_name
    print "Computing reference score for", cset_name
    try:
        fails, prevented, _, patched_scores = test_sample_refpatch(sample_dir, only_n_polls=100)
    except Exception as e:
        print "IGNORING CS THAT CAUSED A test_sample_refpatch EXCEPTION", cset_name, e
        return None
    if fails:
        print "IGNORING CS THAT FAILED ITS OWN POLL TEST", cset_name, "(poll fails:",fails,")"
        return None
    if len(prevented) != len(glob.glob(sample_dir+"/pov/*.xml")+glob.glob(sample_dir+"/pov/*.pov")):
        print "OFFICIAL PATCH FOR ",cset_name," DOES NOT PREVENT ALL PoVs!"
    return patched_scores


def get_reference_scores():
    if os.path.isfile('reference_scores.pickle'):
        with open('reference_scores.pickle', 'rb') as f:
            refs = cPickle.load(f)
    else:
        assert ALLOW_RECOMPUTING
        all_refs = { cs:compute_reference_scores(cs) for cs in os.listdir(SRC_DIR) }
        #all_refs = { cs:compute_reference_scores(cs) for cs in os.listdir(SRC_DIR) if cs.startswith('YAN') } # XXX DEBUG ONLY XXX
        refs = { cs:score for cs,score in all_refs.iteritems() if score is not None }

    # Sanity check
    for scores in refs.values():
        for val in scores.values():
            assert val is not None

    if ALLOW_RECOMPUTING:
        with open('reference_scores.pickle','wb') as f:
            cPickle.dump(refs, f, protocol=cPickle.HIGHEST_PROTOCOL)
    return refs



def ordered_sets(dic):
    """Turns { key: val } into descending OrderedDict { val: set(k1,k2,...) }"""
    sortedvals = sorted(set(dic.values()), reverse=True)
    ret = OrderedDict()
    for i in sortedvals:
        ret[i] = frozenset(k for k,v in dic.iteritems() if v == i)
    return ret


def compare_scores(byus, bydarpa):
    """byus = { team: score }, bydarpa = { team: score }"""
    assert frozenset(byus.keys()) == frozenset(bydarpa.keys())

    our_ranking = ordered_sets(byus)
    darpa_ranking = ordered_sets(bydarpa)

    our_picks = our_ranking.values()[0]
    darpa_picks = darpa_ranking.values()[0]

    from scipy import stats
    # scipy takes them as ordered lists
    teamorder = list(byus.keys())  
    vals_us = [ byus[t] for t in teamorder ]
    vals_darpa = [ bydarpa[t] for t in teamorder ]
    tau, p_value = stats.kendalltau(vals_us, vals_darpa)

    def names(teams_set):
        return '[' + ' '.join(sorted(n.split()[0] for n in teams_set)) + ']'

    if our_picks == darpa_picks:
        print "[  ] All first choice(s)",names(our_picks),"match, excellent!"
    elif our_picks.isdisjoint(darpa_picks):
        print "[XX] Our first choice(s)",names(our_picks)," completely different from DARPA's",names(darpa_picks)
    else:
        print "[__] Partial match between our first choice(s) and DARPA's. Both have",names(darpa_picks&our_picks),"(we also have:",names(our_picks-darpa_picks)," -- darpa also has:",names(darpa_picks-our_picks),")"
    print "     FOR US:"
    for score,teams in our_ranking.iteritems():
        print "       ","%+.4f"%score,names(teams)
    print "     DARPA:"
    for score,teams in darpa_ranking.iteritems():
        print "       ","%+.4f"%score,names(teams)
    print "  %s Kendall tau: %.4f (p-value for being correlated: %.6f)" % (("<7" if tau < 0.7 else "<8") if tau < 0.8 else "  ", tau, p_value)



def main():
    refs = get_reference_scores() # cset -> our scoring of the official patch

    reps = {} # (cset, TeamName) -> our scoring of that team's patch
    if os.path.isfile('replacement_scores.pickle'):
        with open('replacement_scores.pickle', 'rb') as f:
            reps = cPickle.load(f)

    darpa = {} # (cset,TeamName) -> darpa's CSV row
    csets = set() # list of scored cset names

    with open(SCORES_CSV) as f, open('replacement_scores.csv' if ALLOW_RECOMPUTING else '/dev/null','w') as ourf:
        if ALLOW_RECOMPUTING:
            ourcsv = csv.DictWriter(ourf,fieldnames=('TeamName','cset','PerfScore','ExecTimeOverhead','FileSizeOverhead','MemUseOverhead'), extrasaction='ignore')
            ourcsv.writeheader()
        for row in csv.DictReader(f):
            cs = row['cset']
            key = (cs, row['TeamName'])
            darpa[key] = row
            if cs not in refs:
                #print "Skipping", cs
                continue
            print key
            csets.add(cs)
            if key in reps:
                scores = reps[key]
            else:
                if not ALLOW_RECOMPUTING:
                    print "SKIPPING UNSCORED",cs
                    continue
                assert row['package_name'].endswith('.ar')
                rcbs = glob.glob(SUBMISSIONS_DIR+'/'+row['package_name'][:-3]+'/RB*')
                _, _, _, scores = test_sample(rcbs, SRC_DIR+'/'+cs, reference_score=refs[cs], only_n_polls=100)
                reps[key] = scores
            if scores['Scoring algorithm'] != 'CQE':
                print "Skipping, as the scoring algorithm is not the CQE one: ", scores['Scoring algorithm']
                del reps[key]
                continue
            for metric in sorted(set(scores.keys()) & set(row.keys())):
                darpatruth = float(row[metric])
                estimate = float(scores[metric])
                diff = estimate - darpatruth
                print "     %s %20s DARPA: %.2f  estim.: %.2f  (%.2f)" % ("+++" if diff>0.2 else ("---" if diff<-0.2 else "   "), metric, darpatruth, estimate, diff)
            if ALLOW_RECOMPUTING:
                forcsv = scores
                forcsv['cset'] = cs
                forcsv['TeamName'] = row['TeamName']
                ourcsv.writerow(forcsv)


    if ALLOW_RECOMPUTING:
        with open('replacement_scores.pickle','wb') as f:
            cPickle.dump(reps, f, protocol=cPickle.HIGHEST_PROTOCOL)

    for cs in csets:
        teams = [ TeamName for c,TeamName in reps if c == cs ]
        byus = { t:float(reps[(cs,t)][SCORE_TO_COMPARE]) for t in teams }
        bydarpa = { t:float(darpa[(cs,t)][SCORE_TO_COMPARE]) for t in teams }
        print cs
        compare_scores(byus, bydarpa)


if __name__ == "__main__":
    main()
