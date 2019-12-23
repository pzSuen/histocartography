"""Consep Dataset loader."""
import dgl
import torch.utils.data

from histocartography.dataloader.base_dataloader import BaseDataset
from histocartography.utils.io import get_files_in_folder, load_json, complete_path, load_image
from histocartography.graph_building.constants import LABEL, CENTROID


class ConsepDataset(BaseDataset):
    """Consep data loader."""

    def __init__(
        self, path, config, cuda=False, is_train=False
    ):
        """
        Initialize ConsepDataset.

        Args:
            path (str): path to the Consep dataset dir.
            config: (dict) config file
            cuda (bool): cuda usage.
            is_train (bool): training dataset.
        """
        super(ConsepDataset, self).__init__(config, cuda)
        self.is_train = is_train
        self._load_dataset(path)

    def _load_dataset(self, path):
        """
        Load annotations and images
        """
        # 1. load annotations
        ann_fnames = get_files_in_folder(path, 'json')
        self.segmentation_annotations = [
            load_json(
                complete_path(
                    path,
                    fname)) for fname in ann_fnames]
        # 2. load images
        image_fnames = get_files_in_folder(path, 'png')
        self.images = [load_image(complete_path(path, fname))
                       for fname in image_fnames]

    def __getitem__(self, index):
        """
        Get an example.

        Args:
            index (int): index of the example.
        Returns:
            a tuple containing:
                 - dgl graph,
                 - image
                 - labels.
        """

        ann = [{CENTROID: centroid, LABEL: label[0]} for i, (centroid, label) in enumerate(zip(
            self.segmentation_annotations[index]['instance_centroid_location'],
            self.segmentation_annotations[index]['instance_types']))
        ]
        image_size = self.segmentation_annotations[index]['image_dimension']

        g = self.graph_builder(ann, image_size)
        image = self.images[index]
        label = 0
        return g, image, label

    def __len__(self):
        """Return the number of examples."""
        return len(self.images)


def build_dataset(path, *args, **kwargs):
    """
    Build the dataset.

    Returns:
        an ConsepDataset.
    """
    return ConsepDataset(path, *args, **kwargs)


def collate(batch):
    """
    Collate a batch.

    Args:
        batch (torch.tensor): a batch of examples.

    Returns:
        a tuple of torch.tensors.
    """
    graphs = dgl.batch([example[0] for example in batch])
    images = [example[1] for example in batch]
    labels = torch.LongTensor([example[2] for example in batch])
    return graphs, images, labels


def make_data_loader(batch_size, num_workers=1, *args, **kwargs):
    """
    Create a data loader for the dataset.

    Args:
        batch_size (int): size of the batch.
        num_workers (int): number of workers.
    Returns:
        a tuple containing the data loader and the dataset.
    """
    dataset = build_dataset(*args, **kwargs)
    data_loader = torch.utils.data.DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=True,
        collate_fn=collate,
        num_workers=num_workers
    )
    return data_loader, dataset
