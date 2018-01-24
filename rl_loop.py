"""Wrapper script to ensure that main.py commands are called correctly."""
import argh
import argparse
import cloud_logging
import os
import main
import shipname
import sys
from utils import timer
from tensorflow import gfile

# Pull in environment variables. Run `source ./cluster/common` to set these.
BUCKET_NAME = os.environ['BUCKET_NAME']
N = os.environ['BOARD_SIZE']

BASE_DIR = "gs://{}".format(BUCKET_NAME)
MODELS_DIR = os.path.join(BASE_DIR, 'models')
SELFPLAY_DIR = os.path.join(BASE_DIR, 'games')
SGF_DIR = os.path.join(BASE_DIR, 'sgf')
TRAINING_CHUNK_DIR = os.path.join(BASE_DIR, 'data', 'training_chunks')


def print_flags():
    flags = {
        'BUCKET_NAME': BUCKET_NAME,
        'N': N,
        'BASE_DIR': BASE_DIR,
        'MODELS_DIR': MODELS_DIR,
        'SELFPLAY_DIR': SELFPLAY_DIR,
        'SGF_DIR': SGF_DIR,
        'TRAINING_CHUNK_DIR': TRAINING_CHUNK_DIR,
    }
    print("Computed variables are:")
    print('\n'.join('--{}={}'.format(flag, value) for flag, value in flags.items()))

def get_latest_model():
    '''Finds the latest model, returning its model number and name

    Returns: (17, 000017-modelname)
    '''
    all_models = gfile.Glob(os.path.join(MODELS_DIR, '*.meta'))
    model_filenames = [os.path.basename(m) for m in all_models]
    model_numbers_names = [
        (shipname.detect_model_num(m), shipname.detect_model_name(m))
        for m in model_filenames]
    latest_model = sorted(model_numbers_names, reverse=True)[0]
    return latest_model

def game_counts(n=20):
    all_models = gfile.Glob(os.path.join(MODELS_DIR, '*.meta'))
    model_filenames = sorted([os.path.basename(m).split('.')[0] for m in all_models], reverse=True)
    for m in model_filenames[:n]:
        games = gfile.Glob(os.path.join(SELFPLAY_DIR, m, '*.zz'))
        print(m, len(games) * 8)

def bootstrap():
    bootstrap_name = shipname.generate(0)
    bootstrap_model_path = os.path.join(MODELS_DIR, bootstrap_name)
    print("Bootstrapping model at {}".format(bootstrap_model_path))
    main.bootstrap(bootstrap_model_path, n=N)

def selfplay(readouts=800, games=8, verbose=2, resign_threshold=0.99):
    _, model_name = get_latest_model()
    print("Playing a game with model {}".format(model_name))
    model_save_file = os.path.join(MODELS_DIR, model_name)
    game_output_dir = os.path.join(SELFPLAY_DIR, model_name)
    sgf_output_dir = os.path.join(SGF_DIR, model_name)
    main.selfplay(
        load_file=model_save_file,
        output_dir=game_output_dir,
        output_sgf=sgf_output_dir,
        readouts=readouts,
        games=games,
        verbose=verbose,
        n=N,
    )

def gather():
    print("Gathering game output...")
    main.gather(input_directory=SELFPLAY_DIR, output_directory=TRAINING_CHUNK_DIR)

def train(logdir=None):
    model_num, model_name = get_latest_model()
    print("Training on gathered game data, initializing from {}".format(model_name))
    new_model_name = shipname.generate(model_num + 1)
    print("New model will be {}".format(new_model_name))
    load_file = os.path.join(MODELS_DIR, model_name)
    save_file = os.path.join(MODELS_DIR, new_model_name)
    try:
        main.train(TRAINING_CHUNK_DIR, save_file=save_file, load_file=load_file,
               generation_num=model_num, logdir=logdir, n=N)
    except:
        print("got an error!  Muddling on regardless")
        logging.exception("Train error")

def loop(logdir=None):
    gather_errors = 0
    while True:
        with timer("Gather"):
            try:
                gather()
            except:
                gather_errors += 1
                logging.exception("Error in gather, retrying")
                if gather_errors == 3:
                    print("Gathering died too many times!")
                    sys.exit(1)
                continue
        gather_errors = 0

        with timer("Train"):
            train(logdir)

parser = argparse.ArgumentParser()
argh.add_commands(parser, [train, selfplay, gather, bootstrap, loop, game_counts])

if __name__ == '__main__':
    print_flags()
    cloud_logging.configure()
    argh.dispatch(parser)
