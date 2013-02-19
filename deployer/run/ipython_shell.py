#!/usr/bin/env python

def start(settings):
    from IPython import embed
    root = settings()
    embed()

if __name__ == '__main__':
    from deployer.contrib.default_config import example_settings
    start(settings=example_settings)
