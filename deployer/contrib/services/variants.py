from deployer.service import required_property
from deployer.contrib.services.config import Config
from deployer.utils import esc1


class Variants(Config):
    """
    Similar to variants for MacPorts. Variants are conditional modifications
    of installations. They are flags, saved on the target system. If we detect
    that the variants don't match with those that we expect, then we know that
    we have to reinstall the service.
    This is useful, for when some services are installed system-wide from
    several set-ups. Each set-up can add their own variants.  If some variants
    are already in place, and our service adds another variant, then we should
    probably reinstall the service, combining all these variants.
    """
    # Override
    variants = set()
    slug = required_property()

    @property
    def remote_path(self):
        return '/etc/variants/%s' % self.slug

    @property
    def content(self):
        final_variants = self.list(self.variants_final)

        # Return result
        return ' '.join(final_variants)

    def dict(self, var_list):
        if isinstance(var_list, dict):
            return var_list
        var_dict = {}
        for var in var_list:
            var_parts = var.split(':')
            if len(var_parts) == 1:
                var_dict[var_parts[0]] = True
            else:
                var_dict[var_parts[0]] = var_parts[1]
        return var_dict

    def list(self, var_dict):
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
        if self.host.exists(self.remote_path):
            return self.current_content.split()
        return {}


    @property
    def variants_final(self):
        """
        Merge variants installed with requested
        """
        vars_installed = self.dict(self.variants_installed)
        vars_installed.update(self.variants_to_update)
        return vars_installed

    @property
    def variants_to_update(self):
        vars_installed = self.dict(self.variants_installed)
        vars_requested = self.dict(self.variants)
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
