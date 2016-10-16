class Maybe(option):
    def __init__(self, value):
        self.value = value

    def bind (self, fn):
        if self.value is Nothing:


