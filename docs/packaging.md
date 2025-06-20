# Packaging for Sculptor V1

This spec was defined and informed by [this Spec document by
Josh](https://www.dropbox.com/scl/fi/ch5g3upepd2ibytwiq5sh/Sculptor-packaging-spec.paper?rlkey=adynt38yicfj6hhy67lj4ndz4&dl=0)

## Packaging and Distribution Targets

## Our medium-term goal is to provide Sculptor via the Registries

* Python package available from the PyPI manager
* A prebuilt Docker Image available from the Docker Registry containing the environment in which we run Claude code.
* All 3rd-party dependencies as _optional_, that the user will install themselves.

## In the immediate short term, we will support the following two modes for running Sculptor

`uvx --python=3.11 --from https://imbue-sculptor-latest.s3.us-west-2.amazonaws.com/sculptor.tar.gz --refresh sculptor`

And an executable wrapper that the user can download and install on their machine:

```
curl -O https://imbue-sculptor-latest.s3.us-west-2.amazonaws.com/sculptor
chmod +x sculptor
./sculptor --help
```

## In the long term, we may have other plans

Other interesting targets might be OS-level package managers (brew, apt, snap)
or providing direct downloads of pre-built self-contained binary installations.
