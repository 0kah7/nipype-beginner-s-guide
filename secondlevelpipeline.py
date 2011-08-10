"""
Import modules
"""

import nipype.interfaces.freesurfer as fs # freesurfer
import nipype.interfaces.io as nio        # i/o routines
import nipype.interfaces.spm as spm       # spm
import nipype.interfaces.utility as util  # utility
import nipype.pipeline.engine as pe       # pypeline engine


"""
Define experiment specific parameters
"""

#to better access the parent folder of the experiment
experiment_dir = '/mindhive/gablab/u/mnotter/Desktop/TEST'

#tell FreeSurfer where the recon-all output is at
freesurfer_dir = experiment_dir + '/freesurfer_data'
fs.FSCommand.set_default_subjects_dir(freesurfer_dir)

#list of subjectnames
subjects = ['subject1', 'subject2']

#second level analysis pipeline specific components
level2Dir = '/results/level2'
numberOfContrasts = 5 #number of contrasts you specified in the first level analysis
contrast_ids = range(1,numberOfContrasts+1) #to create a list with value [1,2,3,4,5]


"""
Analysis on the Volume
######################
"""

"""
Grab the data
"""

#Node: DataGrabber - to collect all the con images for each contrast
l2volSource = pe.Node(nio.DataGrabber(infields=['con']), name="l2volSource")
l2volSource.inputs.template = experiment_dir + '/results/level1_output/normcons/subject*/con_%04d_ants.nii'
l2volSource.iterables = [('con',contrast_ids)] # iterate over all contrast images
  

"""
Define nodes
"""

#Node: OneSampleTTest - to perform an one sample t-test analysis on the volume
oneSampleTTestVolDes = pe.Node(interface=spm.OneSampleTTestDesign(), name="oneSampleTTestVolDes")

#Node: EstimateModel - to estimate the model
l2estimate = pe.Node(interface=spm.EstimateModel(), name="l2estimate")
l2estimate.inputs.estimation_method = {'Classical' : 1}

#Node: EstimateContrast - to estimate the contrast (in this example just one)
l2conestimate = pe.Node(interface = spm.EstimateContrast(), name="l2conestimate")
cont1 = ('Group','T', ['mean'],[1])
l2conestimate.inputs.contrasts = [cont1]
l2conestimate.inputs.group_contrast = True

#Node: Threshold - to threshold the estimated contrast
l2threshold = pe.Node(interface = spm.Threshold(), name="l2threshold")
l2threshold.inputs.contrast_index = 1
l2threshold.inputs.use_fwe_correction = False
l2threshold.inputs.use_topo_fdr = True
l2threshold.inputs.extent_threshold = 1
#voxel threshold
l2threshold.inputs.extent_fdr_p_threshold = 0.05
#cluster threshold (value is in -ln()): 1.301 = 0.05; 2 = 0.01; 3 = 0.001,
l2threshold.inputs.height_threshold = 3

##Node: MultipleRegressionDesign - to perform a multiple regression analysis
#multipleRegDes = pe.Node(interface=spm.MultipleRegressionDesign(), name="multipleRegDes")
#multipleRegDes.inputs.covariates = [dict(vector=[-0.30,0.52,1.75], #regressor1 for 3 subjects
#                                         name='nameOfRegressor1'),
#                                    dict(vector=[1.55,-1.80,0.77], #regressor2 for 3 subjects
#                                         name='nameOfRegressor2')] 


"""
Establish a second level volume pipeline
"""
   
#Create 2-level vol pipeline and connect up all components
l2volflow = pe.Workflow(name="l2volflow")
l2volflow.base_dir = experiment_dir + level2Dir + '_vol'
l2volflow.connect([(l2volSource,oneSampleTTestVolDes,[('outfiles','in_files')]),
                   (oneSampleTTestVolDes,l2estimate,[('spm_mat_file','spm_mat_file')]),
                   (l2estimate,l2conestimate,[('spm_mat_file','spm_mat_file'),
                                              ('beta_images','beta_images'),
                                              ('residual_image','residual_image')
                                              ]),
                   (l2conestimate,l2threshold,[('spm_mat_file','spm_mat_file'),
                                               ('spmT_images','stat_image'),
                                               ]),
                   ])


"""   
Analysis on the Surface
#######################
"""

"""
Grab the data
"""

#Node: IdentityInterface - to iterate over contrasts and hemispheres
l2surfinputnode = pe.Node(interface=util.IdentityInterface(fields=['contrasts','hemi']),
                          name='l2surfinputnode')
l2surfinputnode.iterables = [('contrasts', contrast_ids),
                             ('hemi', ['lh','rh'])]

#Node: DataGrabber - to collect contrast images and registration files
l2surfSource = pe.Node(interface=nio.DataGrabber(infields=['con_id'],
                                                 outfields=['con','reg']),
                       name='l2surfSource')
l2surfSource.inputs.base_directory = experiment_dir + '/results/level1_output/'
l2surfSource.inputs.template = '*'
l2surfSource.inputs.field_template = dict(con='surf_contrasts/_subject_id_*/con_%04d.img',
                                          reg='bbregister/_subject_id_*/*.dat')
l2surfSource.inputs.template_args = dict(con=[['con_id']],reg=[[]])


"""
Define nodes
"""

#Node: Merge - to merge contrast images and registration files
merge = pe.Node(interface=util.Merge(2, axis='hstack'),name='merge')

#function to create a list of all subjects and the location of their specific files
def ordersubjects(files, subj_list):
    outlist = []
    for subject in subj_list:
        for subj_file in files:
            if '/_subject_id_%s/'%subject in subj_file:
                outlist.append(subj_file)
                continue
    return outlist

#Node: MRISPreproc - to concatenate contrast images projected to fsaverage
concat = pe.Node(interface=fs.MRISPreproc(), name='concat')
concat.inputs.target = 'fsaverage'
concat.inputs.fwhm = 5  #the smoothing of the surface data happens here

#function that transforms a given list into tuples
def list2tuple(listoflist):
    return [tuple(x) for x in listoflist]

#Node: OneSampleTTest - to perform a one sample t-test on the surface
oneSampleTTestSurfDes = pe.Node(interface=fs.OneSampleTTest(), name='oneSampleTTestSurfDes')


"""
Establish a second level surface pipeline
"""

#Create 2-level surf pipeline and connect up all components
l2surfflow = pe.Workflow(name='l2surfflow')
l2surfflow.base_dir = experiment_dir + level2Dir + '_surf'
l2surfflow.connect([(l2surfinputnode,l2surfSource,[('contrasts','con_id')]),
                    (l2surfinputnode,concat,[('hemi','hemi')]),
                    (l2surfSource,merge,[(('con', ordersubjects, subjects),'in1'),
                                         (('reg', ordersubjects, subjects),'in2')]),
                    (merge,concat,[(('out', list2tuple),'vol_measure_file')]),
#                    (concat,oneSampleTTestSurfDes,[('out_file','in_file')]),
	            ])


"""
Datasink (optional)
"""

#Node: Datasink - Create a datasink node to store important outputs
l2datasink = pe.Node(interface=nio.DataSink(), name="l2datasink")
l2datasink.inputs.base_directory = experiment_dir
l2datasink.inputs.container = level2Dir + '_datasink'

#integration of the datasink into the volume analysis pipeline
l2volflow.connect([(l2conestimate,l2datasink,[('spm_mat_file','vol_contrasts.@spm_mat'),
                                              ('spmT_images','vol_contrasts.@T'),
                                              ('con_images','vol_contrasts.@con'),
                                              ]),
                   (l2threshold,l2datasink,[('thresholded_map','vol_contrasts_thresh.@threshold'),
                                            ]),
                   ])

#integration of the datasink into the surface analysis pipeline
l2surfflow.connect([(oneSampleTTestSurfDes,l2datasink,[('sig_file','sig_file')])])


"""
Run pipeline
"""

l2volflow.write_graph(graph2use='flat')
l2volflow.run(plugin='MultiProc', plugin_args={'n_procs' : 2})

l2surfflow.write_graph(graph2use='flat')
l2surfflow.run(plugin='MultiProc', plugin_args={'n_procs' : 2})

