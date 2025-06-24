class Detect_RSCD(Detect_LSCD):
    def __init__(self, nc=80, hidc=256, ch=()):
        super().__init__(nc, hidc, ch)
        self.share_conv = nn.Sequential(DiverseBranchBlock(hidc, hidc, 3), DiverseBranchBlock(hidc, hidc, 3))