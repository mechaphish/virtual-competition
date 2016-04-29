# Virtual Competition

## Dependencies

* Vagrant >= 1.8.1
* VirtualBox >= 5.0


## Run

To initialize VMs and start the competition:

```
vagrant up
vagrant ssh ti
/vagrant/bin/launch start # default options: ROUNDLEN=300 POLLS=100 ROUNDS=100
```


## Update VMs

```
vagrant destroy
vagrant box update
```


## Sync with Darpa repo

```
git remote add upstream https://github.com/CyberGrandChallenge/virtual-competition.git
git checkout upstream
git pull upstream master
```


## About cbtest_wrapper

Jacopo's wrapper around Darpa cb-test.

```
cbtest_wrapper.py -p 3 -i CADET_00003 /path/to/CADET_00003_patched
```

### How good is it?

Still very off in absolute terms. Somewhat compatible in terms of ranking of RCBs, but needs to be checked further.

[reproduce\_cqe\_scores.py](tester/reproduce_cqe_scores.py) measures the CQE (recompiled) official patches and scores team RCBs against them. Ideally, this should match the official results, but we're not there yet. Check the pickle files and the [comparison result](replacement_scores.log).

Note that some of the official patches do not prevent the released PoVs! [replacement\_scores.log](tester/replacement_scores.log)


## Changelog

**IMPORTANT:** Scoring is random!

Changes to DARPA's [virtual-competition](https://github.com/CyberGrandChallenge/virtual-competition):

- better rounds simulation (RB down round on submission, dummy round on new CS release)
- real poll feedbacks
- disabled IDS submission, since we're not running the filter (TODO)
- ti-rotate will also (re-)field official, possibly patched, binaries
- Minor: ti-server checks `MAX_THROWS`, fixed size limits, defaults to our credentials
