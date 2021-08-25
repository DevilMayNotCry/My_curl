# -*- coding: utf-8 -*-
'''
This is a PyTorch implementation of CURL: Neural Curve Layers for Global Image Enhancement
https://arxiv.org/pdf/1911.13175.pdf

Please cite paper if you use this code.

Tested with Pytorch 1.7.1, Python 3.7.9

Authors: Sean Moran (sean.j.moran@gmail.com), 2020

Instructions:

To get this code working on your system / problem you will need to edit the
data loading functions, as follows:

1. main.py, change the paths for the data directories to point to your data
directory 

2. main.py, requires images_train.txt, images_valid.txt, images_test.txt, 
that list the training, validation and test images, one per line of each
txt file

3. data.py, lines 223, 240, 423, 431 change the folder names of the data input and
output directories to point to your folder names. 

We used the Samsung S7 and the Adobe datasets in the paper. They can be 
found at the following URLs:

1. Samsung S7: https://elischwartz.github.io/DeepISP/
2. Adobe5k: https://data.csail.mit.edu/graphics/fivek/

To train the model:

python main.py --valid_every=250 --num_epoch=10000 

With the above arguments, the model will be tested on the validation dataset
every 250 epochs, and the total number of epochs for training will be 10,000.

'''
from sklearn.model_selection import train_test_split
from data import Adobe5kDataLoader, Dataset
import time
import torch
import torchvision.transforms as transforms
from torch.autograd import Variable
import logging
import argparse
import torch.optim as optim
import numpy as np
import datetime
import os.path
import os
import metric
import model
import sys
from torch.utils.tensorboard import SummaryWriter
np.set_printoptions(threshold=sys.maxsize)

def main():

    writer = SummaryWriter()

    timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    log_dirpath = "/content/drive/MyDrive/curl/log/" + timestamp
    os.mkdir(log_dirpath)

    handlers = [logging.FileHandler(
        log_dirpath + "/curl.log"), logging.StreamHandler()]
    logging.basicConfig(
        level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', handlers=handlers)

    parser = argparse.ArgumentParser(
        description="Train the CURL neural network on image pairs")

    parser.add_argument(
        "--num_epoch", type=int, required=False, help="Number of epoches (default 5000)", default=100000)
    parser.add_argument(
        "--valid_every", type=int, required=False, help="Number of epoches after which to compute validation accuracy",
        default=10)
    parser.add_argument(
        "--checkpoint_filepath", required=False, help="Location of checkpoint file", default=None)
    parser.add_argument(
        "--inference_img_dirpath", required=False,
        help="Directory containing images to run through a saved CURL model instance", default=None)
    parser.add_argument(
        "--training_img_dirpath", required=False,
        help="Directory containing images to train a DeepLPF model instance", default="/home/sjm213/adobe5k/adobe5k/")

    args = parser.parse_args()
    num_epoch = args.num_epoch
    valid_every = args.valid_every
    checkpoint_filepath = args.checkpoint_filepath
    inference_img_dirpath = args.inference_img_dirpath
    training_img_dirpath = args.training_img_dirpath

    logging.info('######### Parameters #########')
    logging.info('Number of epochs: ' + str(num_epoch))
    logging.info('Logging directory: ' + str(log_dirpath))
    logging.info('Dump validation accuracy every: ' + str(valid_every))
    logging.info('Training image directory: ' + str(training_img_dirpath))
    logging.info('##############################')


    if (checkpoint_filepath is not None) and (inference_img_dirpath is not None):

        '''
        inference_img_dirpath: the actual filepath should have "input" in the name an in the level above where the images 
        for inference are located, there should be a file "images_inference.txt with each image filename as one line i.e."
        
        images_inference.txt    ../
                                a1000.tif
                                a1242.tif
                                etc
        '''
        img_list = sorted(os.listdir(os.path.join(inference_img_dirpath, 'A')))
        label_list = sorted(os.listdir(os.path.join(inference_img_dirpath, 'B')))
        
        inference_data_loader = Adobe5kDataLoader(data_dirpath=inference_img_dirpath,
                                                  img_ids_filepath=img_list)
        inference_data_dict = inference_data_loader.load_data()
        inference_dataset = Dataset(data_dict=inference_data_dict,
                                    transform=transforms.Compose([transforms.ToTensor()]), normaliser=1,
                                    is_inference=True)

        inference_data_loader = torch.utils.data.DataLoader(inference_dataset, batch_size=1, shuffle=False,
                                                            num_workers=10)

        '''
        Performs inference on all the images in inference_img_dirpath
        '''
        logging.info(
            "Performing inference with images in directory: " + inference_img_dirpath)

        net = model.CURLNet()
        checkpoint = torch.load(checkpoint_filepath, map_location='cuda')
        print(checkpoint)
        net.load_state_dict(checkpoint['model_state_dict'])
        net.eval()

        criterion = model.CURLLoss()

        inference_evaluator = metric.Evaluator(
            criterion, inference_data_loader, "test", log_dirpath)

        inference_evaluator.evaluate(net, epoch=0)

    else:
        img_list = sorted(os.listdir(os.path.join(training_img_dirpath, 'train', 'A')))
        label_list = sorted(os.listdir(os.path.join(training_img_dirpath, 'train', 'B')))

        test_list = sorted(os.listdir(os.path.join(training_img_dirpath, 'test', 'A')))

        training_data, val_data, _, _ = train_test_split(img_list, label_list, test_size=0.05, random_state=7)

        training_data_loader = Adobe5kDataLoader(data_dirpath=os.path.join(training_img_dirpath, 'train'),
                                                 img_ids_filepath=training_data)
        training_data_dict = training_data_loader.load_data()

        training_dataset = Dataset(data_dict=training_data_dict, normaliser=1, is_valid=False)

        validation_data_loader = Adobe5kDataLoader(data_dirpath=os.path.join(training_img_dirpath, 'train'),
                                               img_ids_filepath=val_data)
        validation_data_dict = validation_data_loader.load_data()
        validation_dataset = Dataset(data_dict=validation_data_dict, normaliser=1, is_valid=True)

        testing_data_loader = Adobe5kDataLoader(data_dirpath=os.path.join(training_img_dirpath, 'test'),
                                            img_ids_filepath=test_list)
        testing_data_dict = testing_data_loader.load_data()
        testing_dataset = Dataset(data_dict=testing_data_dict, normaliser=1,is_valid=True)

        training_data_loader = torch.utils.data.DataLoader(training_dataset, batch_size=1, shuffle=True,
                                                       num_workers=6)
        testing_data_loader = torch.utils.data.DataLoader(testing_dataset, batch_size=1, shuffle=False,
                                                      num_workers=6)
        validation_data_loader = torch.utils.data.DataLoader(validation_dataset, batch_size=1,
                                                         shuffle=False,
                                                         num_workers=6)
   
        net = model.CURLNet()
        net.cuda()

        logging.info('######### Network created #########')
        logging.info('Architecture:\n' + str(net))

        for name, param in net.named_parameters():
            if param.requires_grad:
                print(name)

        criterion = model.CURLLoss(ssim_window_size=5)

        '''
        The following objects allow for evaluation of a model on the testing and validation splits of a dataset
        '''
        validation_evaluator = metric.Evaluator(
            criterion, validation_data_loader, "valid", log_dirpath)
        testing_evaluator = metric.Evaluator(
            criterion, testing_data_loader, "test", log_dirpath)

    
        start_epoch=0

        if (checkpoint_filepath is not None) and (inference_img_dirpath is None):
            logging.info('######### Loading Checkpoint #########')
            checkpoint = torch.load(checkpoint_filepath, map_location='cuda')
            net.load_state_dict(checkpoint['model_state_dict'])
            optimizer = optim.Adam(filter(lambda p: p.requires_grad,
                                      net.parameters()), lr=1e-4, betas=(0.9, 0.999), eps=1e-08, weight_decay=1e-10)

            optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
            for g in optimizer.param_groups:
                g['lr'] = 1e-5

            start_epoch = checkpoint['epoch']
            loss = checkpoint['loss']
            net.cuda()
        else:
            optimizer = optim.Adam(filter(lambda p: p.requires_grad,
                                      net.parameters()), lr=1e-4, betas=(0.9, 0.999), eps=1e-08, weight_decay=1e-10)

        best_valid_psnr = 0.0

        alpha = 0.0
        optimizer.zero_grad()
        net.train()

        running_loss = 0.0
        examples = 0
        psnr_avg = 0.0
        ssim_avg = 0.0
        batch_size = 1
        total_examples = 0

        for epoch in range(start_epoch,num_epoch):

            # train loss
            examples = 0.0
            running_loss = 0.0
            
            for batch_num, data in enumerate(training_data_loader, 0):
                print('Epoch: ', epoch, " Batch numer: ", batch_num)
                input_img_batch, gt_img_batch, category = Variable(data['input_img'],
                                                                       requires_grad=False).cuda(), Variable(data['output_img'],
                                                                                                             requires_grad=False).cuda(), data[
                    'name']

                start_time = time.time()
                net_img_batch, gradient_regulariser = net(
                    input_img_batch)
                net_img_batch = torch.clamp(
                    net_img_batch, 0.0, 1.0)

                elapsed_time = time.time() - start_time

                loss = criterion(net_img_batch,
                                 gt_img_batch, gradient_regulariser)

                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

                running_loss += loss.data[0]
                examples += batch_size
                total_examples+=batch_size

                writer.add_scalar('Loss/train', loss.data[0], total_examples)

            logging.info('[%d] train loss: %.15f' %
                         (epoch + 1, running_loss / examples))
            writer.add_scalar('Loss/train_smooth', running_loss / examples, epoch + 1)
            
            model_name = 'epoch_{}.pt'.format(epoch)
            torch.save({
                'epoch': epoch+1,
                'model_state_dict': net.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'loss': loss,
            }, os.path.join(training_img_dirpath, 'models', model_name))
            # Valid loss
            '''
            examples = 0.0
            running_loss = 0.0

            for batch_num, data in enumerate(validation_data_loader, 0):

                net.eval()

                input_img_batch, gt_img_batch, category = Variable(
                    data['input_img'],
                    requires_grad=True).cuda(), Variable(data['output_img'],
                                                         requires_grad=False).cuda(), \
                    data[
                    'name']

                net_img_batch, gradient_regulariser = net(
                    input_img_batch)
                net_img_batch = torch.clamp(
                    net_img_batch, 0.0, 1.0)

                optimizer.zero_grad()

                loss = criterion(net_img_batch,
                                 gt_img_batch, gradient_regulariser)

                running_loss += loss.data[0]
                examples += batch_size
                total_examples+=batch_size
                writer.add_scalar('Loss/train', loss.data[0], total_examples)


            logging.info('[%d] valid loss: %.15f' %
                         (epoch + 1, running_loss / examples))
            writer.add_scalar('Loss/valid_smooth', running_loss / examples, epoch + 1)

            net.train()
            '''
            if (epoch + 1) % valid_every == 0:

                logging.info("Evaluating model on validation dataset")

                valid_loss, valid_psnr, valid_ssim = validation_evaluator.evaluate(
                    net, epoch)
                test_loss, test_psnr, test_ssim = testing_evaluator.evaluate(
                    net, epoch)

                # update best validation set psnr
                if valid_psnr > best_valid_psnr:

                    logging.info(
                        "Validation PSNR has increased. Saving the more accurate model to file: " + 'curl_validpsnr_{}_validloss_{}_testpsnr_{}_testloss_{}_epoch_{}_model.pt'.format(valid_psnr,
                                                                                                                                                                                         valid_loss.tolist()[0], test_psnr, test_loss.tolist()[
                                                                                                                                                                                             0],
                                                                                                                                                                                         epoch))

                    best_valid_psnr = valid_psnr
                    snapshot_prefix = os.path.join(
                        log_dirpath)
                    snapshot_path = snapshot_prefix + '_validpsnr_{}_validloss_{}_testpsnr_{}_testloss_{}_epoch_{}_model.pt'.format(valid_psnr,
                                                                                                                                    valid_loss.tolist()[
                                                                                                                                        0],
                                                                                                                                    test_psnr, test_loss.tolist()[
                                                                                                                                        0],
                                                                                                                                    epoch +1)
                    '''
                    torch.save(net, snapshot_path)
                    '''

                    torch.save({
                        'epoch': epoch+1,
                         'model_state_dict': net.state_dict(),
                        'optimizer_state_dict': optimizer.state_dict(),
                         'loss': loss,
                         }, snapshot_path)

                net.train()


if __name__ == "__main__":
    main()
