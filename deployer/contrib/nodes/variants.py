from deployer.node import required_property
from deployer.contrib.nodes.config import Config
from deployer.utils import esc1


class Variants(Config):
    """
    Simple server-side persistent key-value list of attributes.

    Mostly useful for an installation of a service on a server: what version is
    installed with what options? Do we need to install it again or extend it
    with new options for this extra service?

    Similar to variants for MacPorts. Variants are conditional modifications
    of installations. They are flags, saved on the target system. If we detect
    that the variants don't match with those that we expect, then we know that
    we have to reinstall the service.
    This is useful, for when some services are installed system-wide from
    several set-ups. Each set-up can add their own variants. If some variants
    are already in place, and our service adds another variant, then we should
    probably reinstall the service, combining all these variants.

    Variants can be specified as a list/set or as a dict, but the helper
    attributes convert them to dicts. This allows you to use keys and values,
    which can be compared (like version numbers). It is possible that we will
    drop list support in the future.

    Example:

    variants = ('version:1.2', 'plugin_foo')

    Equivalent:

    variants = {'version': '1.2', 'plugin_foo': True}

    If the server would already contain ('version:1.1', 'plugin_bar'), you know
    you will have to install Version 1.2 with plugins foo and bar to satisfy
    your own service and other services on the same host that depend on it.
    """
    # Override
    variants = set()
    slug = required_property()

    @property
    def remote_path(self):
        return '/etc/variants/%s' % self.slug

    @property
    def content(self):
        final_variants = self._as_list(self.variants_final)

        # Return result
        return ' '.join(final_variants)

    def _as_dict(self, var_list):
        if isinstance(var_list, dict):
            return var_list
        var_dict = {}
        for var in var_list:
            var_parts = var.split(':')
            if len(var_parts) == 1:
                var_dict[var_parts[0]] = True
            elif len(var_parts) > 2:
                raise Exception('Variant %s contains more than one colon' % var)
            else:
                var_dict[var_parts[0]] = var_parts[1]
        return var_dict

    def _as_list(self, var_dict):
        if isinstance(var_dict, list):
            return var_dict
        var_list = []
        for v, s in var_dict.iteritems():
            if not isinstance(s, bool):
                var_list.append('%s:%s' % (v, s))
            else:
                var_list.append(v)
        var_list.sort()
        return var_list

    @property
    def variants_installed(self):
        """
        The currently installed variants.
        """
        if self.host.exists(self.remote_path):
            return self.current_content.split()
        return {}


    @property
    def variants_final(self):
        """
        Merge variants installed with requested.

        If you (re-)install a service, use this as the guide of what to install.
        """
        vars_installed = self._as_dict(self.variants_installed)
        vars_installed.update(self.variants_to_update)
        return vars_installed

    @property
    def variants_to_update(self):
        """
        Compare the installed variants with the variants requested by this service.

        This will return the variants that need to change, with their final
        version. You can check this property to determine whether you need to
        reinstall the service. If you decide to reinstall, use variants_final
        as a guide of what to install, because variants_to_update will not
        include variants that have not changed.
        """
        vars_installed = self._as_dict(self.variants_installed)
        vars_requested = self._as_dict(self.variants)
        vars_to_update = {}
        for var_req, var_spec_req in vars_requested.iteritems():
            if var_req not in vars_installed:
                # The variant is not yet installed
                # Install the requested version
                vars_to_update[var_req] = var_spec_req
            else:
                # The variant is already installed
                if isinstance(var_spec_req, bool):
                    # We do not request a specific version
                    # No need to update
                    pass
                else:
                    var_spec_cur = vars_installed[var_req]
                    # We request a specific version
                    if isinstance(var_spec_cur, bool):
                        # We currently have an unspecified version
                        # Go to the specific version
                        vars_to_update[var_req] = var_spec_req
                    else:
                        # Comparison time!
                        from distutils.version import LooseVersion
                        if LooseVersion(var_spec_cur) < LooseVersion(var_spec_req):
                            # We currently have a lower version, install ours
                            vars_to_update[var_req] = var_spec_req
        return vars_to_update

    @property
    def clear(self):
        """
        Clear (reset) the variants file.
        """
        self.host.sudo("rm '/etc/variants/%s'" % esc1(self.remote_path))

    def setup(self):
        self.host.sudo('mkdir -p /etc/variants')
        Config.setup(self)
