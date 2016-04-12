# Virtual Competition

## Launch

To initialize VMs and start the competition:
```
vagrant up
vagrant ssh ti
/vagrant/bin/launch start
```

Re-run provision:
```
vagrant provision
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

## Changelog

**IMPORTANT:** All feedback and scoring is random!

Changes to DARPA's [virtual-competition](https://github.com/CyberGrandChallenge/virtual-competition):

- disabled IDS submission, since we're not running the filter (TODO)
- ti-rotate will also (re-)field official, possibly patched, binaries
- Minor: ti-server checks `MAX_THROWS`, fixed size limits, defaults to our credentials
- rb submission with rounds simulation and real poll feedbacks