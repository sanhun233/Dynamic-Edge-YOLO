class DCNv2_Offset_Attention(nn.Module):
    def __init__(self, in_channels, kernel_size, stride, deformable_groups=1) -> None:
        super().__init__()

        padding = autopad(kernel_size, None, 1)
        self.out_channel = (deformable_groups * 3 * kernel_size * kernel_size)
        self.conv_offset_mask = nn.Conv2d(in_channels, self.out_channel, kernel_size, stride, padding, bias=True)
        self.attention = MPCA(self.out_channel)

    def forward(self, x):
        conv_offset_mask = self.conv_offset_mask(x)
        conv_offset_mask = self.attention(conv_offset_mask)
        return conv_offset_mask


class DCNv2_MPCA(nn.Module):
    def __init__(self, in_channels, out_channels, kernel_size, stride=1,
                 padding=None, groups=1, dilation=1, act=True, deformable_groups=1):
        super(DCNv2_MPCA, self).__init__()

        self.in_channels = in_channels
        self.out_channels = out_channels
        self.kernel_size = (kernel_size, kernel_size)
        self.stride = (stride, stride)
        padding = autopad(kernel_size, padding, dilation)
        self.padding = (padding, padding)
        self.dilation = (dilation, dilation)
        self.groups = groups
        self.deformable_groups = deformable_groups

        self.weight = nn.Parameter(
            torch.empty(out_channels, in_channels, *self.kernel_size)
        )
        self.bias = nn.Parameter(torch.empty(out_channels))

        self.conv_offset_mask = DCNv2_Offset_Attention(in_channels, kernel_size, stride, deformable_groups)
        self.bn = nn.BatchNorm2d(out_channels)
        self.act = Conv.default_act if act is True else act if isinstance(act, nn.Module) else nn.Identity()
        self.reset_parameters()

    def forward(self, x):
        offset_mask = self.conv_offset_mask(x)
        o1, o2, mask = torch.chunk(offset_mask, 3, dim=1)
        offset = torch.cat((o1, o2), dim=1)
        mask = torch.sigmoid(mask)
        x = torch.ops.torchvision.deform_conv2d(
            x,
            self.weight,
            offset,
            mask,
            self.bias,
            self.stride[0], self.stride[1],
            self.padding[0], self.padding[1],
            self.dilation[0], self.dilation[1],
            self.groups,
            self.deformable_groups,
            True
        )
        x = self.bn(x)
        x = self.act(x)
        return x

    def reset_parameters(self):
        n = self.in_channels
        for k in self.kernel_size:
            n *= k
        std = 1. / math.sqrt(n)
        self.weight.data.uniform_(-std, std)
        self.bias.data.zero_()
        self.conv_offset_mask.conv_offset_mask.weight.data.zero_()
        self.conv_offset_mask.conv_offset_mask.bias.data.zero_()


class Bottleneck_DCNV2_MPCA(Bottleneck):
    """Standard bottleneck with DCNV2."""

    def __init__(self, c1, c2, shortcut=True, g=1, k=(3, 3), e=0.5):  # ch_in, ch_out, shortcut, groups, kernels, expand
        super().__init__(c1, c2, shortcut, g, k, e)
        c_ = int(c2 * e)  # hidden channels
        self.cv2 = DCNv2_MPCA(c_, c2, k[1], 1)


class C3_DCNv2_MPCA(C3):
    def __init__(self, c1, c2, n=1, shortcut=False, g=1, e=0.5):
        super().__init__(c1, c2, n, shortcut, g, e)
        c_ = int(c2 * e)  # hidden channels
        self.m = nn.Sequential(*(Bottleneck_DCNV2_MPCA(c_, c_, shortcut, g, k=(1, 3), e=1.0) for _ in range(n)))


class C2f_DCNv2_MPCA(C2f):
    def __init__(self, c1, c2, n=1, shortcut=False, g=1, e=0.5):
        super().__init__(c1, c2, n, shortcut, g, e)
        self.m = nn.ModuleList(Bottleneck_DCNV2_MPCA(self.c, self.c, shortcut, g, k=(3, 3), e=1.0) for _ in range(n))