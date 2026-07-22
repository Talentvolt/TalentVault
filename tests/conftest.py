import django.template.context

def safe_context_copy(self):
    duplicate = self.__class__.__new__(self.__class__)
    duplicate.__dict__.update(self.__dict__)
    if hasattr(self, 'dicts'):
        duplicate.dicts = [d.copy() if hasattr(d, 'copy') else d for d in self.dicts]
    return duplicate

django.template.context.Context.__copy__ = safe_context_copy
