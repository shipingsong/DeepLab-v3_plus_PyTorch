import time
import torch
from torch.optim import Adam, SGD
from torch.optim.lr_scheduler import MultiStepLR

from module.backbone_network.FCN import FCN8s, FCN16s, FCN32s
from module.utils.metric import Metric
from module.backbone_network.resnet_unet import ResNet_UNet
from module.deeplab_v3 import DeepLab


def train(cfg, net, data_loader, optimizer, criterion, device, epoch, metric):
    net.train()
    num_data = len(data_loader)
    warm_up_epoch = cfg['warm_up_epoch']
    init_lr = cfg['lr']
    confusion_matrix = 0.
    for i_batch, sample in enumerate(data_loader):
        start_time = time.time()
        img, target = sample['image'], sample['label']
        img = img.to(device)
        target = target.to(device)

        optimizer.zero_grad()

        if epoch <= warm_up_epoch:
            adjust_learning_rate_with_warm_up(optimizer, i_batch + (epoch - 1) * num_data,
                                              warm_up_epoch * num_data, init_lr)

        outputs = net(img)

        loss = criterion(outputs, target.long())

        loss.backward()
        optimizer.step()

        if not cfg['auto_adjust_lr']:
            adjust_learning(optimizer, epoch)

        preds = outputs.data.max(1)[1].cpu().numpy()
        confusion_matrix = metric.add(preds=preds, target=target.cpu().numpy(), m=confusion_matrix)
        end_time = time.time() - start_time
        lr = optimizer.param_groups[0]['lr']
        if i_batch % cfg['print_freq'] == 0:
            print("Train/Epoch: {} Iter: {}/{} Loss: {:.4f} "
                  "LR: {:.8f} BatchTime: {:.4f}".format(epoch,
                                                        i_batch, num_data,
                                                        loss.item(),
                                                        lr,
                                                        end_time))

    print("Train mIoU : {}".format(metric.mIoU(m=confusion_matrix)))


def validation(net, data_loader, criterion, device, epoch, metric, print_freq):
    net.eval()
    num_data = len(data_loader)
    confusion_matrix = 0.
    with torch.no_grad():
        for i_batch, sample in enumerate(data_loader):
            img, target = sample['image'], sample['label']
            img = img.to(device)
            target = target.to(device)

            outputs = net(img)
            # outputs = F.softmax(outputs)
            loss = criterion(outputs, target.long())
            preds = outputs.data.max(1)[1].cpu().numpy()
            confusion_matrix = metric.add(preds=preds, target=target.cpu().numpy(), m=confusion_matrix)

            if i_batch % print_freq == 0:
                print("Validate/Epoch: {} Iter: {}/{} Loss: {:.4f}".format(epoch,
                                                                           i_batch, num_data,
                                                                           loss.item()))
        print("Validation mIoU : {}".format(metric.mIoU(m=confusion_matrix)))


def adjust_learning_rate_with_warm_up(optimizer, n, num_iter, init_lr):
    """"""
    lr = 1e-6 + (init_lr - 1e-6) / num_iter * n
    for param_group in optimizer.param_groups:
        param_group['lr'] = lr


def adjust_learning(optimizer, epoch):
    """Adjust Learning"""
    if epoch <= 5:
        for param_group in optimizer.param_groups:
            param_group['lr'] = 5e-3
    elif epoch <= 10:
        for param_group in optimizer.param_groups:
            param_group['lr'] = 1e-4
    elif epoch <= 15:
        for param_group in optimizer.param_groups:
            param_group['lr'] = 5e-5
    else:
        for param_group in optimizer.param_groups:
            param_group['lr'] = 1e-5


def build_train(cfg, data_loader, val_loader,
                criterion, device):
    if cfg['mode'] == 'fcn-8s':
        net = FCN8s(cfg['num_classes'])
    elif cfg['mode'] == 'fcn-16s':
        net = FCN16s(cfg['num_classes'])
    elif cfg['mode'] == 'fcn-32s':
        net = FCN32s(cfg['num_classes'])
    elif cfg['mode'] == 'U-Net':
        net = ResNet_UNet('resnet-50', cfg['num_classes'])
    elif cfg['mode'] == 'DeepLab-v3+':
        net = DeepLab('aligned_inception', stride=16, num_classes=cfg['num_classes'])
    else:
        raise NotImplementedError

    torch.backends.cudnn.benchmark = True
    net.to(device)
    if cfg['n_gpu'] > 1:
        net = torch.nn.DataParallel(net, device_ids=[0, 1, 2])

    if cfg['pretrain']:
        net.load_state_dict(torch.load(cfg['model_path']))

    if cfg['optim'] == 'Adam':
        optimizer = Adam(net.parameters(),
                         lr=cfg['lr'],
                         weight_decay=cfg['weight_decay'])
    elif cfg['optim'] == 'SGD':
        optimizer = SGD(net.parameters(),
                        lr=cfg['lr'],
                        momentum=cfg['momentum'],
                        weight_decay=cfg['weight_decay'])
    else:
        raise NotImplementedError

    if cfg['auto_adjust_lr']:
        lr_scheduler = MultiStepLR(optimizer, milestones=cfg['milestones'], gamma=0.1)
    metric = Metric(cfg['num_classes'])

    for epoch in range(1, cfg['epoch'] + 1):
        train(cfg, net, data_loader, optimizer, criterion, device, epoch, metric)
        # validate the net of performance
        validation(net, val_loader, criterion, device, epoch, metric, cfg['print_freq'])

        if cfg['auto_adjust_lr']:
            lr_scheduler.step()
        torch.save(net.state_dict(), cfg['save_path'] + '/Lane_%s.pth' % epoch)
