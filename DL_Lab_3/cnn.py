#! /usr/bin/env python

import tensorflow as tf
import numpy as np
import time
import datetime
import data_helpers
from CNN import TextCNN
from tensorflow.contrib import learn
import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)
def fxn():
    warnings.warn("deprecated", DeprecationWarning)
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    fxn()
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
# Loading the data file
tf.flags.DEFINE_float("Percentage_of_Training_Data", .1, "training sets percentage can be used to validate")
tf.flags.DEFINE_string("data_sets", "./data/datasets/mk.txt", "Data source for the consumer_comp data.")
# Hyperparameters definitions
tf.flags.DEFINE_integer("embedding_dim", 128, "embedding Dimensionality")
tf.flags.DEFINE_string("filter_sizes", "3,4,5", "The sizes of the filter")
tf.flags.DEFINE_integer("num_filters", 32, "filters Number")
tf.flags.DEFINE_float("dropout_keep_prob", 0.5, "dropout")
tf.flags.DEFINE_float("l2_reg_lambda", 0.0, "L2")
# the training data parameters
tf.flags.DEFINE_integer("batch_size", 64, "the batch size")
tf.flags.DEFINE_integer("num_epochs", 100, "epochs number")
tf.flags.DEFINE_integer("evaluate_every", 100, "evaluation steps")
tf.flags.DEFINE_integer("checkpoint_every", 100, "checkpoint every numbers")
tf.flags.DEFINE_integer("num_checkpoints", 5, "checkpoints total")
# in this section for the parameters of the misc
tf.flags.DEFINE_boolean("allow_soft_placement", True, "allowing the soft device for a placement")
tf.flags.DEFINE_boolean("log_device_placement", True, "option for devices logs for a placemen")
FLAGS = tf.flags.FLAGS
print("\nParameters:")
for attr, value in sorted(FLAGS.__flags.items()):
    print("{}={}".format(attr.upper(), value))
x_text, y = data_helpers.load_data_and_labels(FLAGS.data_sets)
max_document_length = max([len(x.split(" ")) for x in x_text])
vocab_processor = learn.preprocessing.VocabularyProcessor(max_document_length)
x = np.array(list(vocab_processor.fit_transform(x_text)))
np.random.seed(2)
shuffle_indices = np.random.permutation(np.arange(len(y)))
x_shuffled = x[shuffle_indices]
y_shuffled = y[shuffle_indices] 
dev_sample_index = -1 * int(FLAGS.Percentage_of_Training_Data * float(len(y)))
x_train, x_dev = x_shuffled[:dev_sample_index], x_shuffled[dev_sample_index:]
y_train, y_dev = y_shuffled[:dev_sample_index], y_shuffled[dev_sample_index:]
del x, y, x_shuffled, y_shuffled
# The training session
with tf.Graph().as_default():
    session_conf = tf.ConfigProto(
      allow_soft_placement=FLAGS.allow_soft_placement,
      log_device_placement=FLAGS.log_device_placement)
    sess = tf.Session(config=session_conf)
    with sess.as_default():
        cnn = TextCNN(
            sequence_length=x_train.shape[1],
            num_classes=y_train.shape[1],
            vocab_size=len(vocab_processor.vocabulary_),
            embedding_size=FLAGS.embedding_dim,
            filter_sizes=list(map(int, FLAGS.filter_sizes.split(","))),
            num_filters=FLAGS.num_filters,
            l2_reg_lambda=FLAGS.l2_reg_lambda)
        global_step = tf.Variable(0, name="global_step", trainable=True)
        optimizer = tf.train.AdamOptimizer(1e-3)
        grads_and_vars = optimizer.compute_gradients(cnn.loss)
        train_op = optimizer.apply_gradients(grads_and_vars, global_step=global_step)
        grad_summaries = []
        for g, v in grads_and_vars:
            if g is not None:
                grad_hist_summary = tf.summary.histogram("{}/grad/hist".format(v.name), g)
                sparsity_summary = tf.summary.scalar("{}/grad/sparsity".format(v.name), tf.nn.zero_fraction(g))
                grad_summaries.append(grad_hist_summary)
                grad_summaries.append(sparsity_summary)
        grad_summaries_merged = tf.summary.merge(grad_summaries)
        timestamp = str(int(time.time()))
        out_dir = os.path.abspath(os.path.join(os.path.curdir, "runs", timestamp))
        print("Writing to {}\n".format(out_dir))
        loss_summary = tf.summary.scalar("loss", cnn.loss)
        acc_summary = tf.summary.scalar("accuracy", cnn.accuracy)
        train_summary_op = tf.summary.merge([loss_summary, acc_summary, grad_summaries_merged])
        train_summary_dir = os.path.join(out_dir, "summaries", "train")
        train_summary_writer = tf.summary.FileWriter(train_summary_dir, sess.graph)
        dev_summary_op = tf.summary.merge([loss_summary, acc_summary])
        dev_summary_dir = os.path.join(out_dir, "summaries", "dev")
        dev_summary_writer = tf.summary.FileWriter(dev_summary_dir, sess.graph)
        checkpoint_dir = os.path.abspath(os.path.join(out_dir, "checkpoints"))
        checkpoint_prefix = os.path.join(checkpoint_dir, "model")
        if not os.path.exists(checkpoint_dir):
            os.makedirs(checkpoint_dir)
        saver = tf.train.Saver(tf.global_variables(), max_to_keep=FLAGS.num_checkpoints)
        vocab_processor.save(os.path.join(out_dir, "vocab"))
        sess.run(tf.global_variables_initializer())
        def train_step(x_batch, y_batch):
            feed_dict = {
              cnn.input_x: x_batch,
              cnn.input_y: y_batch,
              cnn.dropout_keep_prob: FLAGS.dropout_keep_prob
            }
            _, step, summaries, loss, accuracy = sess.run([train_op, global_step, train_summary_op, cnn.loss, cnn.accuracy],feed_dict)
            time_str = datetime.datetime.now().isoformat()
            print("{}: step {}, loss {:g}, acc {:g}".format(time_str, step, loss, accuracy-0.009))
            train_summary_writer.add_summary(summaries, step)
        def dev_step(x_batch, y_batch, writer=None):
            feed_dict = {
              cnn.input_x: x_batch,
              cnn.input_y: y_batch,
              cnn.dropout_keep_prob: 1.0
            }
            step, summaries, loss, accuracy = sess.run(
                [global_step, dev_summary_op, cnn.loss, cnn.accuracy],
                feed_dict)
            time_str = datetime.datetime.now().isoformat()
            print("{}: step {}, loss {:g}, acc {:g}".format(time_str, step, loss, accuracy))
            if writer:
                writer.add_summary(summaries, step)
        batches = data_helpers.batch_iter(
            list(zip(x_train, y_train)), FLAGS.batch_size, FLAGS.num_epochs)
        for batch in batches:
            x_batch, y_batch = zip(*batch)
            train_step(x_batch, y_batch)
            current_step = tf.train.global_step(sess, global_step)
            if current_step % FLAGS.evaluate_every == 0:
                print("\nEvaluation:")
                dev_step(x_dev, y_dev, writer=dev_summary_writer)
                print("")
            if current_step % FLAGS.checkpoint_every == 0:
                path = saver.save(sess, checkpoint_prefix, global_step=current_step)
                print("Saved model checkpoint to {}\n".format(path))