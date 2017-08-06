# -*- coding: utf-8 -*-
'''
Semi-Supervised Learning with Deep Generative Models - Kingma et al 2014

This work is absolutely not an effort to reproduce exact results of the cited paper, nor I confine my implementations to the suggestion of the original authors.
I have tried to implement my own limited understanding of the original paper in hope to get a better insight into their work. 
Use this code with no warranty and please respect the accompanying license.
'''

import sys
sys.path.append('../common')

from tools_config import data_dir, expr_dir
import os
import matplotlib.pyplot as plt
from tools_train import get_train_params, OneHot, vis_square
from datetime import datetime
from tools_general import tf, np
from tools_networks import deconv, conv, dense, dropout
   
def concat_labels(X, labels):
    if X.get_shape().ndims == 4:
        X_shape = tf.shape(X)
        labels_reshaped = tf.reshape(labels, [-1, 1, 1, 10])
        a = tf.ones([X_shape[0], X_shape[1], X_shape[2], 10])
        X = tf.concat([X, labels_reshaped * a], axis=3)
    return X

def create_VAE_E(Xin, labels, is_training, Cout=1, trainable=True, reuse=False, networktype='vaeE'):
    '''Xin: batchsize * H * W * Cin
       labels: batchsize * num_classes
       output1-2: batchsize * Cout'''
    
    with tf.variable_scope(networktype, reuse=reuse):
        
        Xin = concat_labels(Xin, labels)
        
        Eout = conv(Xin, is_training, kernel_w=4, stride=2, Cout=64, pad=1, trainable=trainable, act='reLu', norm='batchnorm', name='deconv1')  # 14*14
        Eout = conv(Eout, is_training, kernel_w=4, stride=2, Cout=128, pad=1, trainable=trainable, act='reLu', norm='batchnorm', name='deconv2')  # 7*7
        
        posteriorMu = dense(Eout, is_training, trainable=trainable, Cout=Cout, act=None, norm=None, name='dense_mean')
        posteriorSigma = dense(Eout, is_training, trainable=trainable, Cout=Cout, act=None, norm=None, name='dense_var')
    return posteriorMu, posteriorSigma
     
def create_VAE_D(z, labels, is_training, Cout=1, trainable=True, reuse=False, networktype='vaeD'):
    '''z : batchsize * latend_dim 
       labels: batchsize * num_classes
        output: batchsize * 28 * 28 * 1'''
    with tf.variable_scope(networktype, reuse=reuse):
        z = tf.concat(axis=-1, values=[z, labels])
        Gz = dense(z, is_training, Cout=4 * 4 * 256, act='reLu', norm='batchnorm', name='dense1')
        Gz = tf.reshape(Gz, shape=[-1, 4, 4, 256])  # 4
        Gz = deconv(Gz, is_training, kernel_w=5, stride=2, Cout=256, trainable=trainable, act='reLu', norm='batchnorm', name='deconv1')  # 11
        Gz = deconv(Gz, is_training, kernel_w=5, stride=2, Cout=128, trainable=trainable, act='reLu', norm='batchnorm', name='deconv2')  # 25
        Gz = deconv(Gz, is_training, kernel_w=4, stride=Cout, Cout=1, act=None, norm=None, name='deconv3')  # 28
        Gz = tf.nn.sigmoid(Gz)
    return Gz

def create_vae_trainer(base_lr=1e-4, networktype='VAE', latendDim=100):
    '''Train a Variational AutoEncoder'''
    eps = 1e-5
    
    is_training = tf.placeholder(tf.bool, [], 'is_training')

    inZ = tf.placeholder(tf.float32, [None, latendDim])
    inL = tf.placeholder(tf.float32, [None, 10])
    inX = tf.placeholder(tf.float32, [None, 28, 28, 1])

    posteriorMu, posteriorSigma = create_VAE_E(inX, inL, is_training, Cout=latendDim, trainable=True, reuse=False, networktype=networktype + '_vaeE') 
    
    Z = posteriorSigma * inZ + posteriorMu
    Xrec = create_VAE_D(Z, inL, is_training, trainable=True, reuse=False, networktype=networktype + '_vaeD')
    Xrec_test = create_VAE_D(inZ, inL, is_training, trainable=True, reuse=True, networktype=networktype + '_vaeD')
    
    # E[log P(X|z)]
    reconstruction_loss = tf.reduce_sum((inX -1.0) * tf.log(1.0 - Xrec + eps) - inX * tf.log(Xrec + eps), reduction_indices = [1,2,3])
    # D_KL(Q(z|X) || P(z|X))
    KL_QZ = 0.5 * tf.reduce_sum( tf.exp(posteriorSigma) + tf.square(posteriorMu) - 1 - posteriorSigma, reduction_indices = 1) 
    
    total_loss = tf.reduce_mean( reconstruction_loss + KL_QZ)  
    
    vaetrain = tf.train.AdamOptimizer(learning_rate=base_lr, beta1=0.9).minimize(total_loss)

    return vaetrain, total_loss, is_training, inZ, inX, inL, Xrec, Xrec_test, posteriorMu

if __name__ == '__main__':
    networktype = 'cVAE_MNIST'
    
    batch_size = 128
    base_lr = 1e-5
    epochs = 60
    latendDim = 2
    
    work_dir = expr_dir + '%s/%s/' % (networktype, datetime.strftime(datetime.today(), '%Y%m%d'))
    if not os.path.exists(work_dir): os.makedirs(work_dir)
    
    data, max_iter, test_iter, test_int, disp_int = get_train_params(data_dir + '/' + networktype, batch_size, epochs=epochs, test_in_each_epoch=1, networktype=networktype)
    
    tf.reset_default_graph() 
    sess = tf.InteractiveSession()
    
    vaetrain, total_loss, is_training, inZ, inX, inL, Xrec, Xrec_test, posteriorMu = create_vae_trainer(base_lr, networktype=networktype, latendDim=latendDim)
    tf.global_variables_initializer().run()
    
    
    var_list = [var for var in tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES) if (networktype.lower() in var.name.lower()) and ('adam' not in var.name.lower())]  
    saver = tf.train.Saver(var_list=var_list, max_to_keep=100)
    # saver.restore(sess, expr_dir + 'ganMNIST/20170707/214_model.ckpt') 
     
    best_test_loss = np.inf 
 
    train_loss = np.zeros(max_iter)
    test_loss = np.zeros(int(np.ceil(max_iter / test_int)))
 
    Z_test = np.random.normal(size=[batch_size, latendDim], loc=0.0, scale=1.).astype(np.float32)
    labels_test = OneHot(np.random.randint(10, size=[batch_size]), n=10)    
          
    for it in range(max_iter): 
        Z = np.random.normal(size=[batch_size, latendDim], loc=0.0, scale=1.).astype(np.float32)
  
        if it % test_int == 0:  # Record summaries and test-set accuracy
            accumulated_loss = 0.0 
            for i_test in range(test_iter):
                X, labels = data.test.next_batch(batch_size)
                
                recloss = sess.run(total_loss, feed_dict={inX:X, inL:labels, inZ: Z, is_training:False})
                accumulated_loss = np.add(accumulated_loss, recloss)
                 
            test_loss[it // test_int] = np.divide(accumulated_loss, test_iter)
     
            print("Iteration #%4d, testing .... Test Loss = %f" % (it, test_loss[it // test_int]))
            if test_loss[it // test_int] < best_test_loss:
                best_test_loss = test_loss[it // test_int]
                print('################ Best Results yet.[loss = %2.5f] saving results...' % best_test_loss)
                vaeD_sample = sess.run(Xrec_test, feed_dict={inL:labels_test, inZ: Z_test , is_training:False})
                vis_square(vaeD_sample[:121], [11, 11], save_path=work_dir + 'Iter_%d.jpg' % it)
                saver.save(sess, work_dir + "%.3d_model.ckpt" % it)
         
        X, labels = data.train.next_batch(batch_size)
        recloss, _ = sess.run([total_loss, vaetrain], feed_dict={inX:X, inL:labels, inZ: Z, is_training:True})
         
        train_loss[it] = recloss
        if it % disp_int == 0:print("Iteration #%4d, Train Loss = %f" % (it, recloss))