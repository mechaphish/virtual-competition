#!/usr/bin/env python

import glob
import os
import subprocess
import argparse
import json

# TODO: NOT SURE AT ALL THAT THE PERFORMANCE SCORING IS CORRECT
#       Also, the full algorithm for CFE is not even out yet.
#
# Docs:
#   - FAQ 58 and 59
#   - https://github.com/CyberGrandChallenge/cgc-release-documentation/blob/master/walk-throughs/scoring-cbs.md
#   - https://github.com/CyberGrandChallenge/cgc-release-documentation/blob/master/CQE%20Scoring.pdf
#   - https://github.com/CyberGrandChallenge/cgc-release-documentation/blob/master/ti-api-spec.txt


def compute_overhead_scores(replacement_scores, reference_scores, cqe_scoring_alg):
    """Given performance sums, computes the resulting scores. Mix of the walk-through and CQE_Scoring.pdf. Also see test_polls (for the score dict format)."""

    if replacement_scores['number_of_polls_used'] == reference_scores['number_of_polls_used']:
        # As in walk-throughs/scoring-cbs.md
        REPcpuclock = float(replacement_scores['cpuclock_sum'])
        REPmaxrss = float(replacement_scores['maxrss_sum'])
        REPminflt = float(replacement_scores['minflt_sum'])
        REPfilesize = float(replacement_scores['filesize_sum'])
        REFcpuclock = float(reference_scores['cpuclock_sum'])
        REFmaxrss = float(reference_scores['maxrss_sum'])
        REFminflt = float(reference_scores['minflt_sum'])
        REFfilesize = float(reference_scores['filesize_sum'])
    else:
        # Use the averages
        REPcpuclock = replacement_scores['cpuclock_avg']
        REPmaxrss = replacement_scores['maxrss_avg']
        REPminflt = replacement_scores['minflt_avg']
        REPfilesize = replacement_scores['filesize_avg']
        REFcpuclock = reference_scores['cpuclock_avg']
        REFmaxrss = reference_scores['maxrss_avg']
        REFminflt = reference_scores['minflt_avg']
        REFfilesize = reference_scores['filesize_avg']

    if None in (REPcpuclock,REFcpuclock,REPfilesize,REFfilesize,REPmaxrss,REFmaxrss,REPminflt,REFminflt):
        # None of the polls passed, or not enough data
        return {'ScoringAlgorithm': 'NOT ENOUGH DATA, DID ANY POLL PASS?'}

    # Again, as in the walk-through.
    # Matches CQE_Scoring.pdf, except for mem_use
    ExecTimeOverhead = REPcpuclock / REFcpuclock - 1
    FileSizeOverhead = REPfilesize / REFfilesize - 1
    MemUseOverhead = 0.5 * (REPmaxrss / REFmaxrss + REPminflt / REFminflt) - 1

    # As in CQE_Scoring.pdf
    # TODO: CFE version
    assert cqe_scoring_alg
    assert replacement_scores.get('ScoringAlgorithm','CQE') == 'CQE'
    assert reference_scores.get('ScoringAlgorithm','CQE') == 'CQE'
    PerfFactor = 1 + max(0.25 * FileSizeOverhead, MemUseOverhead, ExecTimeOverhead)
    assert PerfFactor >= 0
    if PerfFactor < 1.10:
        PerfScore = 1
    elif PerfFactor < 1.62:
        PerfScore = (PerfFactor - 0.1) ** -4
    elif PerfFactor < 2:
        PerfScore = (-0.493*PerfFactor + 0.986)
    else:
        PerfScore = 0

    return {
            'ExecTimeOverhead': ExecTimeOverhead,
            'FileSizeOverhead': FileSizeOverhead,
            'MemUseOverhead': MemUseOverhead,
            'PerfFactor': PerfFactor,
            'PerfScore': PerfScore,
            'ScoringAlgorithm': 'CQE'
           }


def cb_test(cbs, *extra_args):
    """
    Wrapper around the official cb-test
    :param cbs: list of CB paths. Must all be in the same directory.
    :param extra_args: extra args for cb-test (Note: include '--negotiate' for CFE binaries)
    :return: returncode, stdout
    TODO: Aravind was copying everything to a temporary directory, is it actually necessary? The makefile doesn't do it.
    """
    assert isinstance(cbs,(tuple,list))
    cmd = ['cb-test'] # '--debug'
    cbs_directory = os.path.dirname(cbs[0])
    cmd += ('--directory', cbs_directory)
    cmd += ('--cb',)
    for cb in cbs:
        assert os.path.dirname(cb) == cbs_directory
        cmd += (os.path.basename(cb),)
    cmd.extend(extra_args)

    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, close_fds=True)
    out, _ = p.communicate()

    if os.path.isfile(cbs_directory+'/core'):
        os.unlink(cbs_directory+'/core') # Making sure it's not left around
                                         # TODO: should we try to get and return one?
    return p.returncode, out


def parse_cb_single_test_out(output_buf):
    """
    Parse the output of cb-test ON A SINGLE TESTCASE to get various performance counters.
    NOTE: Based on Aravind's, but filesize was probably incorrect if there were multiple CBs,
          and all values were probably overwritten if there was more than one XML or CB.
          This one sums instead of overwriting, and should handle correctly multi-CB challenge sets.
          Interpreting and combining scores of different testcases is left to the other functions.
          (Explicitly renamed outputs to match the docs and ensure no confusion.
           test_polls is the one with comparable output.)
    :param output_buf: Output of cb test
    :return: final_result (single letter indicating final result of the test)
            , Dictionary containing performance metrics in the following format:
                    "maxrss": <long>
                    "minflt": <long>
                    "cpuclock": <long>
                    "taskclock": <long>
                    "utime": <float>
            }
    """
    final_result = None
    measurement = {}

    # Performance counters
    # Format: (key check, split value, json key, type)
    performance_counters = {("cb-server: total maxrss", "total maxrss", "maxrss", long),
                            ("cb-server: total minflt", "total minflt", "minflt", long),
                            ("cb-server: total sw-cpu-clock", "sw-cpu-clock", "cpuclock", long),
                            ("cb-server: total sw-task-clock", "sw-task-clock", "taskclock", long),
                            ("cb-server: total utime", "utime", "utime", float),
                           }
    total_failed = -1
    for curr_line in output_buf.split("\n"):
        for curr_perf_tuple in performance_counters:
            if (curr_perf_tuple[0] in curr_line) and len(curr_line.split(curr_perf_tuple[1])) > 1:
                assert curr_perf_tuple[2] not in measurement
                str_val = curr_line.split(curr_perf_tuple[1])[1].strip()
                converted_val = curr_perf_tuple[3](str_val)
                measurement[curr_perf_tuple[2]] = converted_val
        if "total tests failed" in curr_line:
            total_failed = int(curr_line.split(":")[1])
        elif "SIGSEGV" in curr_line or "SIGFPE" in curr_line or "SIGILL" in curr_line:
            final_result = "C"
        elif "SIGALRM" in curr_line or "not ok - process timed out" in curr_line:
            final_result = "F"
    if not set(measurement.keys()) == set(c[2] for c in performance_counters):
        print 'WARNING: missing performance counter metrics'
        print 'expected:', set(c[2] for c in performance_counters)
        print 'received:', set(measurement.keys())

    if total_failed > 0:
        final_result = "F"
    elif final_result is None:
        final_result = "S"

    return final_result, measurement



def test_polls(cbs, poll_xmls, reference_scores=None, *extra_test_args):
    """
    Success check and performance estimate on modified CBs.
    :param cbs: list of the custom CB paths
    :param poll_xmls: Paths to (pre-built) polls to try.
    :param reference_score: scores for the reference binary, if known
    :param extra_test_args: extra args for cb-test (Note: include '--negotiate' for CFE binaries)
    :return:   failed_polls
             , performance_avg (averages, kept similar to Aravind's parse_cb_test_out)
             , scores (with sums as in docs, includes overhead estimates if possible)
    """

    # 1. Keeps the sum of all metrics
    #    This seems the best reproduction of the docs, wrt rounding.
    # Note: keeps running on failure, differently from directly passing --xml_dir to cb-test.
    failed_polls = []; num_ok_polls = 0
    maxrss_sum = 0L; minflt_sum = 0L; taskclock_sum = 0L; cpuclock_sum = 0L; utime_sum = 0.0; filesize_sum = 0L
    for cb in cbs:
        st = os.stat(cb)
        filesize_sum += st.st_size
        if not os.access(cb, os.X_OK):
            import stat
            os.chmod(cb, stat.S_IMODE(st.st_mode) | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    for xml in poll_xmls:
        ret, out = cb_test(cbs, '--xml', xml, *extra_test_args)
        result_letter, perf = parse_cb_single_test_out(out)
        if ret == 0:
            assert result_letter == 'S'
            maxrss_sum += perf['maxrss']
            minflt_sum += perf['minflt']
            taskclock_sum += perf['taskclock']
            cpuclock_sum += perf['cpuclock']
            utime_sum += perf['utime']
            num_ok_polls += 1
        else:
            failed_polls.append(xml)

    # 2. However, if some polls fail we can't compare CS results use the sums.
    #    Let's have averages ready for that case.
    #    (Also, I think this is what was planned to go into the db).
    if num_ok_polls:
        maxrss_avg = float(maxrss_sum) / num_ok_polls
        minflt_avg = float(minflt_sum) / num_ok_polls
        taskclock_avg = float(taskclock_sum) / num_ok_polls
        cpuclock_avg = float(cpuclock_sum) / num_ok_polls
        utime_avg = float(utime_sum) / num_ok_polls
    else:
        # Nothing to estimate!
        maxrss_avg = None; minflt_avg = None; taskclock_avg = None; cpuclock_avg = None; utime_avg = None
    filesize_avg = float(filesize_sum) / len(cbs)

    # 3. Estimate the overhead score, if possible
    scores = {
        # Base measurement sums, named like in scoring-cbs.md
        'taskclock_sum': taskclock_sum,
        'cpuclock_sum': cpuclock_sum,
        'utime_sum': utime_sum,
        'filesize_sum': filesize_sum,
        'maxrss_sum': maxrss_sum,
        'minflt_sum': minflt_sum,
        'taskclock_avg': taskclock_avg,
        'cpuclock_avg': cpuclock_avg,
        'utime_avg': utime_avg,
        'filesize_avg': filesize_avg,
        'maxrss_avg': maxrss_avg,
        'minflt_avg': minflt_avg,
        'number_of_polls_used': num_ok_polls
    }
    if reference_scores:
        scores.update(compute_overhead_scores(scores, reference_scores, cqe_scoring_alg=True))
    return failed_polls, {'perf': {'rss':maxrss_avg, 'flt':minflt_avg, 'taskClock':taskclock_avg, 'cpuClock':cpuclock_avg, 'filesize':filesize_avg}}, scores


def test_povs(cbs, povs, *extra_test_args):
    """
    POV-prevention check on modified CBs.
    :param cbs: list of the custom CB paths
    :param povs: paths to pre-built POVs. Make sure they use the right format and file extension.
    :param extra_test_args: extra args for cb-test (Note: include '--negotiate' for CFE binaries)
    :return:   prevented_povs
    """
    prevented_povs = []
    for pov in povs:
        ret, out = cb_test(cbs, '--xml', pov, *extra_test_args)
        result_letter, _ = parse_cb_single_test_out(out)
        if ret == 0:
            assert result_letter == 'S'
            prevented_povs.append(pov)
    return prevented_povs


def test_sample(cbs, sample_dir, reference_score=None, only_n_polls=None):
    """
    Combo of 'make check' and performance estimate on modified CBs.
    Will call test_polls and test_povs using inputs from that known sample.
    Adapted from cb-testing/cgc-cb.mk
    :param cbs: list of the custom CB paths
    :param sample_dir: original (pre-built) DARPA sample dir
    :param reference_score: scores for the reference binary, if known
    :param only_n_polls: uses only N polls instead of the usual 1000
    :return:   failed_polls
             , prevented_povs
             , performance_json (see parse_cb_test_out)
             , scores (sums as in docs, includes overhead estimates if possible)
    """

    # Straight from cgc-cb.mk:
    has_cfe_pov = bool(glob.glob(sample_dir+'/pov_*')) or bool(glob.glob(sample_dir+'/pov/*.povxml'))
    extra_test_args = ('--negotiate',) if has_cfe_pov else ()

    poll_xmls = []
    if os.path.isdir(sample_dir+'/poller/for-testing'):
        poll_xmls += glob.glob(sample_dir+'/poller/for-testing/*.xml')
    if os.path.isdir(sample_dir+'/poller/for-release'):
        poll_xmls += glob.glob(sample_dir+'/poller/for-release/*.xml')
    assert poll_xmls

    if only_n_polls:
        poll_xmls = sorted(poll_xmls)[:only_n_polls]

    # Excludes .povxml, which always have to be compiled
    povs = glob.glob(sample_dir + "/pov/*.pov") + glob.glob(sample_dir + "/pov/*.xml")

    assert povs

    failed_polls, performance_json, scores = test_polls(cbs, poll_xmls, reference_score, *extra_test_args)
    prevented_povs = test_povs(cbs, povs, *extra_test_args)
    return failed_polls, prevented_povs, performance_json, scores


def test_sample_refpatch(sample_dir, *args, **kwargs):
    """test_sample(official patched version for sample_dir)"""
    return test_sample(glob.glob(sample_dir+"/bin/*_patched"), sample_dir, *args, **kwargs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--polls", type=int, default=None,
                        help="number of polls to run")
    parser.add_argument("-i", "--csid",
                        help="CSID")
    parser.add_argument("-d", "--directory", default="/vagrant/shared/cgc-challenges/",
                        help="challenges directory")
    parser.add_argument("binary",
                        help="path of binary to test")
    args = parser.parse_args()

    d = os.path.join(args.directory, args.csid)

    result = {}
    reference_fails, reference_prevented, reference_avg, reference_scores = test_sample_refpatch(d, only_n_polls=args.polls)
    # assert not reference_fails
    assert len(reference_prevented) == len(glob.glob(d+"/pov/*.xml")+glob.glob(d+"/pov/*.pov"))
    # One-by-one CB test (incorrect for multi-CBs)
    tested_fails, tested_prevented, tested_avg, tested_scores = test_sample((args.binary,), d, reference_score=reference_scores, only_n_polls=args.polls)

    result['reference'] = {
        'fails': reference_fails,
        'prevented': reference_prevented,
        'performance': reference_avg,
        'scores': reference_scores,
    }
    result['tested'] = {
        'fails': tested_fails,
        'prevented': tested_prevented,
        'performance': tested_avg,
        'scores': tested_scores,
    }
    print json.dumps(result, indent=2)
