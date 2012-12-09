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
        # Read the existing variants.
        if self.host.exists(self.remote_path):
            current_variants = self.current_content.split()
        else:
            current_variants = []

        # Combine and sort
        ordered_variants = list(set(list(self.variants) + current_variants))
        ordered_variants.sort()

        # Return result
        return ' '.join(ordered_variants)

    @property
    def clear(self):
        """
        Clear (reset) the variants file.
        """
        self.host.sudo("rm '/etc/variants/%s'" % esc1(self.remote_path))

    def setup(self):
        self.host.sudo('mkdir /etc/variants')
        Config.setup(self)
