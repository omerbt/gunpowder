import copy
import logging
import numpy as np

from .batch_filter import BatchFilter
from gunpowder.volume import Volume, VolumeTypes

logger = logging.getLogger(__name__)

class PrepareMalis(BatchFilter):
    ''' Creates a component label volume needed for two-phase malis training.

    Args:

        labels_volume_type(:class:`VolumeType`): The label volume to use.

        ignore_volume_type(:class:`VolumeType`): An ignore mask to use, if it 
            appears in the batch.

        malis_comp_volume_type(:class:`VolumeType`): The malis component volume 
            to generate.
    '''

    def __init__(self, labels_volume_type=None, ignore_volume_type=None, malis_comp_volume_type=None):

        if labels_volume_type is None:
            labels_volume_type = VolumeTypes.GT_LABELS
        if ignore_volume_type is None:
            ignore_volume_type = VolumeTypes.GT_IGNORE
        if malis_comp_volume_type is None:
            malis_comp_volume_type = VolumeTypes.MALIS_COMP_LABEL

        self.labels_volume_type = labels_volume_type
        self.ignore_volume_type = ignore_volume_type
        self.malis_comp_volume_type = malis_comp_volume_type
        self.skip_next = False

    def setup(self):
        self.upstream_spec = self.get_upstream_provider().get_spec()
        self.spec = copy.deepcopy(self.upstream_spec)

        # only give warning that GT_LABELS is missing, in prepare() when checked that node is not skipped
        if self.labels_volume_type in self.spec.volumes:
            self.spec.volumes[self.malis_comp_volume_type] = self.spec.volumes[self.labels_volume_type]

    def get_spec(self):
        return self.spec

    def prepare(self, request):

        # MALIS_COMP_LABEL has to be in request for PrepareMalis to run
        if not self.malis_comp_volume_type in request.volumes:
            logger.warn("no {} requested, will do nothing".format(self.malis_comp_volume_type))
            self.skip_next = True
        else:
            assert self.labels_volume_type in request.volumes, "PrepareMalis requires GT_LABELS, but they are not in request"
            del request.volumes[self.malis_comp_volume_type]

    def process(self, batch, request):

        # do nothing if MALIS_COMP_LABEL is not in request
        if self.skip_next:
            self.skip_next = False
            return

        gt_labels = batch.volumes[self.labels_volume_type]
        next_id = gt_labels.data.max() + 1

        gt_pos_pass = gt_labels.data

        if self.ignore_volume_type in batch.volumes:

            gt_neg_pass = np.array(gt_labels.data)
            gt_neg_pass[batch.volumes[self.ignore_volume_type].data==0] = next_id

        else:

            gt_neg_pass = gt_pos_pass

        batch.volumes[self.malis_comp_volume_type] = Volume(data=np.array([gt_neg_pass, gt_pos_pass]),
                                                             roi=request.volumes[self.labels_volume_type])

        # Why don't we update gt_affinities in the same way?
        # -> not needed
        #
        # GT affinities are all 0 in the masked area (because masked area is
        # assumed to be set to background in batch.gt).
        #
        # In the negative pass:
        #
        #   We set all affinities inside GT regions to 1. Affinities in masked
        #   area as predicted. Belongs to one forground region (introduced
        #   above). But we only count loss on edges connecting different labels
        #   -> loss in masked-out area only from outside regions.
        #
        # In the positive pass:
        #
        #   We set all affinities outside GT regions to 0 -> no loss in masked
        #   out area.
