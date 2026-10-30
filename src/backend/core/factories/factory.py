"""Small factory builders the provider and repository registries use."""
def build_from_settings(cls):
    def factory(item):
        return cls(item)

    return factory

def build_from_settings_local(cls):
    def factory(item, service_settings):
        return cls(item, service_settings)
    return factory

def build_repo_bundle(**repo_classes):
    def factory(session):
        return {
            name: repo_cls(session)
            for name, repo_cls in repo_classes.items()
        }

    return factory