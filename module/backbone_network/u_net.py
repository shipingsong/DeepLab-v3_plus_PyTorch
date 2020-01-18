import torch
import torch.nn as nn
from torchvision.models.resnet import resnet18, resnet34, \
    resnet50, resnet101, resnet152, Bottleneck, BasicBlock


class Encoder(nn.Module):
    def __init__(self, backbone):
        super().__init__()
        self.backbone = backbone
        self.layer0 = nn.Sequential(
            nn.Conv2d(3, 64, 3, stride=1, padding=1, bias=False),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.Conv2d(64, 64, 3, stride=1, padding=1, bias=False),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        h1 = self.layer0(x)
        h2 = self.backbone.maxpool(h1)
        h2 = self.backbone.layer1(h2)
        h3 = self.backbone.layer2(h2)
        h4 = self.backbone.layer3(h3)
        h5 = self.backbone.layer4(h4)

        return h1, h2, h3, h4, h5


class ConvBNReLU(nn.Sequential):
    def __init__(self, planes):
        super().__init__(
            nn.Conv2d(planes[0], planes[1], 3, padding=1, bias=False),
            nn.BatchNorm2d(planes[1]),
            nn.ReLU(inplace=True),
            nn.Conv2d(planes[1], planes[2], 3, padding=1, bias=False),
            nn.BatchNorm2d(planes[2]),
            nn.ReLU(inplace=True),
        )


class Decoder(nn.Module):
    def __init__(self, inplanes, planes):
        super().__init__()
        # up-sample : h5 -> h4
        self.up4 = nn.ConvTranspose2d(inplanes[0], planes[0], 4, 2, 1)
        self.layer4 = ConvBNReLU(planes=[planes[0] * 2, planes[0], planes[0] // 2])
        # up-sample : h4 -> h3
        self.up3 = nn.ConvTranspose2d(inplanes[1], inplanes[1], 4, 2, 1)
        self.layer3 = ConvBNReLU(planes=[inplanes[1] * 2, inplanes[1], planes[1]])
        # up-sample : h3 -> h2
        self.up2 = nn.ConvTranspose2d(inplanes[2], inplanes[2], 4, 2, 1)
        self.layer2 = ConvBNReLU(planes=[inplanes[2] * 2, inplanes[2], planes[2]])
        # up-sample : h2 -> h1
        self.up1 = nn.ConvTranspose2d(inplanes[3], inplanes[3], 4, 2, 1)
        self.layer1 = ConvBNReLU(planes=[inplanes[3] * 2, inplanes[3], planes[3]])

    def forward(self, x):
        h4 = self.up4(x[4])
        # up-sample = 2
        h4 = torch.cat((x[3], h4), 1)
        h4 = self.layer4(h4)
        h3 = self.up3(h4)
        # up-sample = 4
        h3 = torch.cat((x[2], h3), 1)
        h3 = self.layer3(h3)
        h2 = self.up2(h3)
        # up-sample = 8
        h2 = torch.cat((x[1], h2), 1)
        h2 = self.layer2(h2)
        h1 = self.up1(h2)
        # up-sample = 16
        h1 = torch.cat((x[0], h1), 1)
        out = self.layer1(h1)

        return out


class UNet(nn.Module):
    def __init__(self, backbone, num_classes=21):
        super().__init__()
        if backbone == 'resnet-18':
            self.backbone = resnet18()
            self.in_channel = [512, 128, 64, 64]
            self.out_channel = [256, 64, 64, 64]
        elif backbone == 'resnet-34':
            self.backbone = resnet34()
            self.in_channel = [512, 128, 64, 64]
            self.out_channel = [256, 64, 64, 64]
        elif backbone == 'resnet-50':
            self.backbone = resnet50()
            self.in_channel = [2048, 512, 256, 64]
            self.out_channel = [1024, 256, 64, 64]
        elif backbone == 'resnet-101':
            self.backbone = resnet101()
            self.in_channel = [2048, 512, 256, 64]
            self.out_channel = [1024, 256, 64, 64]
        elif backbone == 'resnet-152':
            self.backbone = resnet152()
            self.in_channel = [2048, 512, 256, 64]
            self.out_channel = [1024, 256, 64, 64]
        else:
            raise NotImplementedError

        self.encoder = Encoder(self.backbone)
        self.decoder = Decoder(self.in_channel, self.out_channel)
        self.out = nn.Conv2d(64, num_classes, 1)

    def forward(self, x):
        x = self.encoder(x)
        x = self.decoder(x)
        x = self.out(x)

        return x


inputs = torch.randn(1, 3, 224, 224)
net = UNet('resnet-152')
output = net(inputs)
print(output.size())