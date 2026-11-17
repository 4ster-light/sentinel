# Helper for building the COPR source RPM.
#
# `make srpm` downloads the release tarball referenced by Source0 and writes
# an SRPM into this directory:
#
#   make srpm
#
# Upload the result with
#   copr-cli build 4ster-light/sentinel-pm sentinel-pm-<version>-1.src.rpm
#
# `dist` is cleared when the SRPM is created so the same NVR is built in every
# COPR chroot instead of inheriting the dist tag of the machine that created
# the SRPM.

SPEC    := sentinel-pm.spec
SOURCES := $(CURDIR)/SOURCES

# Take the archive from the spec's Source0 so the spec stays authoritative.
SRCURL  := $(shell rpmspec -P $(SPEC) | sed -n 's/^Source0:[[:space:]]*//p' | head -n1)
TARBALL := $(notdir $(SRCURL))

.PHONY: srpm tarball clean

srpm: tarball
	rpmbuild -bs \
		--define "_sourcedir $(SOURCES)" \
		--define "_srcrpmdir $(CURDIR)" \
		--define 'dist %{nil}' \
		$(SPEC)

tarball:
	mkdir -p $(SOURCES)
	test -s $(SOURCES)/$(TARBALL) || curl -fsSL -o $(SOURCES)/$(TARBALL) $(SRCURL)

clean:
	rm -f *.src.rpm
