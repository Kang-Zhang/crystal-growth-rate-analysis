# Improvements to consider:
# give option for time identifier string in case time=*s wasn't followed
# give option to calibrate image length from window pixel width (based on known image window length), or just manually give a micron/pixel value
###################################################################
# Imports
import os
import glob
import pickle
from collections import OrderedDict
import pandas as pd
import numpy as np
from sys import platform as sys_pf
import matplotlib
if sys_pf == 'darwin':
    matplotlib.use("TkAgg") # This fixes crashes on mac
import matplotlib.pyplot as plt
from scipy import ndimage, misc
from scipy.signal import argrelextrema
from scipy.optimize import curve_fit
# sci-kit image
from skimage import exposure
from skimage.color import rgb2gray
from skimage.filters.rank import median
from skimage.morphology import disk
from skimage.measure import profile_line
# GUI imports
import os
import csv
import time
import datetime
import tkinter as tk
from tkinter import LEFT, RIGHT, W, E, N, S, INSERT, END, BOTH
from tkinter.filedialog import (askopenfilename, askdirectory,
                             askopenfilenames)
from tkinter.ttk import Style,Treeview, Scrollbar, Checkbutton
# Plotting specifics
# UI
from matplotlib.backends.backend_tkagg import (FigureCanvasTkAgg,
                                         NavigationToolbar2Tk)
from matplotlib.figure import Figure
# Scalebar
from mpl_toolkits.axes_grid1.anchored_artists import AnchoredSizeBar
import matplotlib.font_manager as fm
# Misc.
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.widgets import SpanSelector
from matplotlib.ticker import AutoMinorLocator, MaxNLocator
from matplotlib.patches import Rectangle
# Colors
from palettable.tableau import Tableau_10
from palettable.colorbrewer.qualitative import Set1_9
# local code imports
import imageHelper

#plt.style.use('ggplot')
# styleDir = os.path.join(os.path.expanduser('~'),
            # 'Google Drive','Research',
            # 'Templates','matplotlib')
#plt.style.use(os.path.join(styleDir,'origin2.mplstyle.py'))
#import warnings
# Install moviepy via conda install -c conda-forge moviepy
# from moviepy.editor import VideoFileClip
# from moviepy.video.fx.all import crop
#warnings.filterwarnings('ignore')
matplotlib.rc("savefig",dpi=100)
################################################################################

def setNiceTicks(ax,Nx=4,Ny=4,yminor=2,xminor=2,
               tick_loc=('both','both'),logx=False,logy=False):
    # If one of the axes is log, just use defaults
    # Things get screwy on log scales with these locators
    # tick_loc = (x,y) where x is 'both','top',or'bottom'
    #             y is 'both','left','right'
    if not logx:
        ax.xaxis.set_minor_locator(AutoMinorLocator(xminor))
        ax.xaxis.set_major_locator(MaxNLocator(Nx))

    if not logy:
        ax.yaxis.set_minor_locator(AutoMinorLocator(yminor))
        ax.yaxis.set_major_locator(MaxNLocator(Ny))

    # set tick length/width if desired
    ax.tick_params(grid_alpha=0)
    #ax.tick_params(direction='in', length=5, width=1.5, colors='k',
    #           grid_color='gray', grid_alpha=0.5)
    #ax.tick_params(direction='in', length=2.5, width=1, colors='k',which='minor')
    # set ticks at top and right of plot if desired
    if tick_loc:
        ax.xaxis.set_ticks_position(tick_loc[0])
        ax.yaxis.set_ticks_position(tick_loc[1])
    else:
        ax.set_xticks([])
        ax.set_yticks([])

def threshold_crop_denoise(img_file,x1,x2,y1,y2,threshold_lower,threshold_upper,
                        d,rescale=None,img=None,equalize_hist=False,
                        threshold_out=False,multiple_ranges=False,clip_limit=0.05):
    ''' threshold_crop_denoise
    This function crops an image, then thresholds and denoises it
    x1,x2,y1,y2 define crop indices
    image_file is an image filename to be loaded
    Alternatively, a numpy array of a gray scale image can be passed in as img
    rescale and equalize_hist allow contrast enhancement to be performed before
        thresholding
    threshold_out inverts the threshold so that pixel values outside the region
        are set to True
    multiple_ranges allows for multiple pixel ranges to be threshold (logical or)
        If this is selected, threshold_lower and _upper must be lists of equal length
    '''
    # Read image in gray scale (mode='L'), unless a pre-loaded image is passed
    if img == None:
        img=misc.imread(img_file,mode='L')
    if rescale:
        img = exposure.rescale_intensity(img,in_range=rescale)
    if equalize_hist:
        img = exposure.equalize_adapthist(img,clip_limit=clip_limit)
        img = 255 * img
    # Crop
    cropped = img[y1:y2,x1:x2]
    # Threshold above or below given pixel intensity
    # This converts image to black and white
    if not multiple_ranges:
        if not threshold_out:
            thresholded = np.logical_and(cropped>threshold_lower,cropped<threshold_upper)
        else:
            thresholded = np.logical_or(cropped<threshold_lower,cropped>threshold_upper)
    else:
        if not threshold_out:
            thresholded = np.logical_and(cropped>threshold_lower[0],cropped<threshold_upper[0])
            for r_idx in range(1,len(threshold_lower)):
                temp = np.logical_and(cropped>threshold_lower[r_idx],cropped<threshold_upper[r_idx])
                thresholded = np.logical_or(thresholded,temp)
        else:
            thresholded = np.logical_or(cropped<threshold_lower[0],cropped>threshold_upper[0])
            for r_idx in range(1,len(threshold_lower)):
                temp = np.logical_or(cropped<threshold_lower[r_idx],cropped>threshold_upper[r_idx])
                thresholded = np.logical_and(thresholded,temp)


    # Despeckle with disk size d
    denoised = median(thresholded, disk(d))
    return denoised,thresholded,cropped

def set_new_im_data(ax,im_data,new_img):
    # Change data extent to match new image
    im_data.set_extent((0, new_img.shape[1], new_img.shape[0], 0))
    # Reset axes limits
    ax.set_xlim(0,new_img.shape[1])
    ax.set_ylim(new_img.shape[0],0)
    # Now set the data
    im_data.set_data(new_img)

# Calibration values for Nikon microscope
micron_per_pixel = {'4x':1000/696, '10x':1000/1750,
                  '20x':500/1740, '50x':230/2016}
# This is obtained by multiplying micron_per_pixel by 2048,
# which is the pixel width for images saved by the Lumenera software
image_width_microns = {'4x':  2942.5,
                         '20x':  588.5,
                         '10x': 1170.3,
                         '50x':  233.7}
def get_growth_edge(img,line,length_per_pixel):
    # Get line profile
    profile = profile_line(img,
                           (line[0][1],line[0][0]),
                           (line[1][1],line[1][0]))
    # Find last point on grain (where image is still saturated)
    growth_front_endpoint = np.where(profile==np.amax(profile))[0][-1]
    line_endpoint = profile.shape[0]
    # Get total line length
    total_line_length = imageHelper.get_line_length(
                            line,mag='20x',unit='um',
                            length_per_pixel=length_per_pixel)
    # Distance to growth front is the fraction of the line up to the last point
    distance_to_growth_front = (total_line_length
                             * (growth_front_endpoint+1) # +1 accounts for index starting at 0
                             / line_endpoint)
    return distance_to_growth_front



class GrowthRateAnalyzer(tk.ttk.Frame):
    def __init__(self,parent):
        tk.ttk.Frame.__init__(self, parent)
        self.parent = parent
        self.root = tk.ttk.Frame
        # Initialization booleans
        self.crop_initialized = False
        self.threshold_initialized = False
        self.save_initialized = False
        self.df_file = None
        self.base_dir = os.getcwd()
        # Default dir for troubleshooting purposes
        #self.base_dir = 'C:/Users/JSB/Google Drive/Research/Data/Gratings/2018-06-11_TPBi_30nm_rate_depend/0.1_Aps/10x_timeseries/'
        # initialize dataframe save location
        self.df_dir = os.path.join(os.getcwd(),'dataframes')
        if not os.path.isdir(self.df_dir):
            os.mkdir(self.df_dir)
        self.configure_gui()
    def configure_gui(self):
        # Master Window
        self.parent.title("Growth Rate Analysis")
        self.style = Style()
        self.style.theme_use("default")
        # Lay out all the Frames
        file_container = tk.ttk.Frame(self.parent)
        file_container.pack()
        # Create a frame to hold sample properties and the plotter
        sample_props_and_plot_container = tk.ttk.Frame(self.parent)
        sample_props_and_plot_container.pack()
        sample_props_container = tk.ttk.Frame(sample_props_and_plot_container)
        sample_props_container.pack(side=LEFT)
        plotContainer = tk.ttk.Frame(sample_props_and_plot_container)
        plotContainer.pack(side=LEFT)#fill=BOTH, expand=True
        crop_container = tk.ttk.Frame(self.parent)
        crop_container.pack()
        threshold_plot_container = tk.ttk.Frame(self.parent)
        threshold_plot_container.pack(fill=BOTH, expand=True)
        threshold_container = tk.ttk.Frame(self.parent)
        threshold_container.pack()
        # Open directory prompt
        self.l_file_directory = tk.Label(file_container,
                                 text='Time Series Directory')
        self.l_file_directory.grid(row=0, column=0, sticky=W)
        self.t_file_dir = tk.Text(file_container)
        self.t_file_dir.configure(height = 1, width=70)
        self.t_file_dir.grid(row=0, column=1, sticky=W)
        self.b_getDir = tk.ttk.Button(file_container, command=self.get_directory_click)
        self.b_getDir.configure(text="Open Dir.")
        self.b_getDir.grid(row=0, column=2, sticky=W)
        # Open file
        self.b_getFile = tk.ttk.Button(file_container, command=self.get_images_click)
        self.b_getFile.configure(text="Open Files")
        self.b_getFile.grid(row=0, column=3, sticky=W)
        # Sample properties
        # Used as metadata in save dataframe
        self.sample_props =  OrderedDict([
                           ('growth_date',
                             {'label':'Growth Date:',
                              'default_val':'yyyy-m-dd',
                              'type':'Entry',
                              'dtype':'string'}),
                           ('material',
                             {'label':'Material (Sep by /):',
                              'default_val':'TPBi',
                              'type':'Entry',
                              'dtype':'string'}),
                           ('thickness_nm',
                             {'label':'Thickness (nm) (Sep by /):',
                              'default_val':'30',
                              'type':'Entry',
                              'dtype':'float'}),
                           ('deposition_rate_aps',
                             {'label':'Deposition Rate (A/s):',
                              'default_val':'1',
                              'type':'Entry',
                              'dtype':'float'}),
                           ('deposition_temp_c',
                             {'label':'Deposition Temp (C):',
                              'default_val':'25',
                              'type':'Entry',
                              'dtype':'float'}),
                           ('anneal_temp_c',
                             {'label':'Anneal Temp (C):',
                              'default_val':'165',
                              'type':'Entry',
                              'dtype':'float'}),
                           ('substrate',
                             {'label':'Substrate:',
                              'default_val':'Si',
                              'type':'Entry',
                              'dtype':'string'}),
                           ('note',
                             {'label':'Note:',
                              'default_val':'None',
                              'type':'Entry',
                              'dtype':'string'})
                           ])
        self.s_sample_props={}
        self.e_sample_props = ['']*len(self.sample_props)
        row_idx=0
        for key,input_dict in self.sample_props.items():
            tk.Label(sample_props_container,text=input_dict['label']).grid(row=row_idx,column=0)
            self.s_sample_props[key] = tk.StringVar()
            self.s_sample_props[key].set(input_dict['default_val'])
            if input_dict['type']=='Entry':
                self.e_sample_props[row_idx] = tk.Entry(sample_props_container,
                                             textvariable=self.s_sample_props[key],width=10)
            # If this is a lock-in test and an option menu is selected,
            # populate the options via lockinSettingsOptions
            # and call command to write setting
            elif input_dict['type']=='OptionMenu':
                self.e_sample_props[row_idx]=tk.OptionMenu(
                                        sample_props_container,
                                        self.s_sample_props[key],
                                        *self.sample_props[key]['options'])
            self.e_sample_props[row_idx].grid(row=row_idx,column=1)
            row_idx+=1
        # self.l_sample_props = ['']*len(labels)
        # self.e_sample_props = ['']*len(labels)
        # self.s_sample_props = ['']*len(labels)
        # for index,label in enumerate(labels):
            # self.l_sample_props[index] = tk.Label(sample_props_container, text=label)
            # self.l_sample_props[index].grid(row=index, column=0, sticky=W)
            # self.s_sample_props[index] = tk.StringVar()
            # self.s_sample_props[index].set(defaults[index])
            # self.e_sample_props[index] = tk.Entry(
                                        # sample_props_container,
                                        # textvariable=self.s_sample_props[index])
            # self.e_sample_props[index].grid(row=index,column=1)

        # Crop region plot
        self.fig, self.ax = plt.subplots(ncols=2,figsize=(7,2.5),
                                     gridspec_kw = {'width_ratios':[1, 1.1]})
        self.fig.subplots_adjust(wspace=0.29,left=0.01,bottom=0.17,top=.95,right=0.75)
        self.canvas = FigureCanvasTkAgg(self.fig, master=plotContainer)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=BOTH, expand=True)
        self.toolbar = NavigationToolbar2Tk(self.canvas, plotContainer)
        self.toolbar.update()

        # Crop Region buttons
        #self.fileDirLabel = tk.Label(file_container, text = 'Pick image files')
        #self.fileDirLabel.grid(row=1, column=0, sticky=W)
        self.b_plotCrop = tk.ttk.Button(crop_container, command=self.pick_crop_region)
        self.b_plotCrop.configure(text="Pick Crop")
        self.b_plotCrop.grid(row=0, column=0, sticky=W)
        self.b_getRanges = tk.ttk.Button(crop_container, command=self.get_axes_ranges)
        self.b_getRanges.configure(text="Get Crop Region")
        self.b_getRanges.grid(row=0, column=1, sticky=E)
        self.l_crop_range = tk.Label(crop_container, text = 'x1=?, x2=?, y1=?, y2=?')
        self.l_crop_range.grid(row=0, column=2, sticky=W)

        tk.Label(crop_container,text="Image Mag").grid(row=0,column=3)
        self.s_mag=tk.StringVar()
        self.s_mag.set('10x')
        self.e_mag=tk.OptionMenu(crop_container,self.s_mag,
                           *['4x','10x','20x','50x'])
        self.e_mag.grid(row=0,column=4)

        self.b_draw_lines = tk.ttk.Button(crop_container,
                                command=self.draw_line_segments)
        self.b_draw_lines.configure(text="Pick Directions")
        self.b_draw_lines.grid(row=0, column=5, sticky=W)

        self.b_get_lines = tk.ttk.Button(crop_container, command=self.get_line_segments)
        self.b_get_lines.configure(text="Get Directions")
        self.b_get_lines.grid(row=0, column=6, sticky=E)

        self.b_check_edge = tk.ttk.Button(crop_container, command=self.check_edge_detection)
        self.b_check_edge.configure(text="Check Edge Detection")
        self.b_check_edge.grid(row=1, column=0, sticky=W)

        tk.Label(crop_container,text="Get time from:").grid(row=1,column=1)
        self.s_time_source = tk.StringVar()
        self.s_time_source.set('Date Modified')
        self.e_time_source = tk.OptionMenu(crop_container,self.s_time_source,
                                *['Date Modified','Filename (time=*s)'])
        self.e_time_source.grid(row=1,column=2)

        self.b_extract_growth = tk.ttk.Button(crop_container, command=self.extract_growth_rates)
        self.b_extract_growth.configure(text="Extract Growth Rates")
        self.b_extract_growth.grid(row=1, column=3, sticky=E)

        self.b_pick_df = tk.ttk.Button(crop_container, command=self.pick_df)
        self.b_pick_df.configure(text="Pick DF")
        self.b_pick_df.grid(row=1, column=4, sticky=W)

        self.b_save_results = tk.ttk.Button(crop_container, command=self.save_results)
        self.b_save_results.configure(text="Save Results")
        self.b_save_results.grid(row=1, column=5, sticky=W)
        # Threshold figure
        self.threshold_fig,self.threshold_ax = plt.subplots(ncols=4,
                                                      figsize=(10,2.5))
        self.threshold_fig.subplots_adjust(wspace=0.3,top=0.8)
        self.threshold_canvas = FigureCanvasTkAgg(
                                    self.threshold_fig,
                                    master=threshold_plot_container)
        self.threshold_canvas.draw()
        self.threshold_canvas.get_tk_widget().pack(fill = BOTH, expand = True)
        #self.toolbar = NavigationToolbar2Tk(self.threshold_canvas, threshold_plot_container)
        #self.toolbar.update()
        tk.Label(threshold_container,text="Threshold").grid(row=1,column=0)
        tk.Label(threshold_container,text="Lower").grid(row=0,column=1)
        tk.Label(threshold_container,text="Upper").grid(row=0,column=2)
        tk.Label(threshold_container,text="Disk").grid(row=0,column=3)
        tk.Label(threshold_container,text="Inv. Thresh?").grid(row=0,column=4)
        tk.Label(threshold_container,text="Multi Ranges?").grid(row=0,column=5)
        tk.Label(threshold_container,text="Eq. Hist?").grid(row=0,column=6)
        tk.Label(threshold_container,text="Clip Limit").grid(row=0,column=7)

        self.s_threshold_lower=tk.StringVar()
        self.s_threshold_lower.set('60')
        self.e_s_threshold_lower=tk.Entry(threshold_container,
                                   textvariable=self.s_threshold_lower,width=5)
        self.e_s_threshold_lower.grid(row=1,column=1)

        self.s_threshold_upper=tk.StringVar()
        self.s_threshold_upper.set('70')
        self.e_s_threshold_upper=tk.Entry(threshold_container,
                                   textvariable=self.s_threshold_upper,width=5)
        self.e_s_threshold_upper.grid(row=1,column=2)

        self.s_disk=tk.StringVar()
        self.s_disk.set('5')
        self.e_disk=tk.Entry(threshold_container,textvariable=self.s_disk,width=5)
        self.e_disk.grid(row=1,column=3)

        self.bool_threshold_out = tk.BooleanVar()
        self.bool_threshold_out.set(False)
        self.e_threshold_out = tk.Checkbutton(
                                threshold_container,
                                variable=self.bool_threshold_out,
                                onvalue=True,offvalue=False)
        self.e_threshold_out.grid(row=1,column=4)

        self.bool_multi_ranges = tk.BooleanVar()
        self.bool_multi_ranges.set(False)
        self.e_multi_ranges = tk.Checkbutton(
                                threshold_container,
                                variable=self.bool_multi_ranges,
                                onvalue=True,offvalue=False)
        self.e_multi_ranges.grid(row=1,column=5)

        self.bool_eq_hist = tk.BooleanVar()
        self.bool_eq_hist.set(True)
        self.e_eq_hist = tk.Checkbutton(threshold_container,variable=self.bool_eq_hist,
                                  onvalue = True, offvalue = False,
                                  command=self.eq_hist_cb_command)
        self.e_eq_hist.grid(row=1,column=6)

        self.s_clip_limit = tk.StringVar()
        self.s_clip_limit.set('0.05')
        self.last_clip_limit=self.s_clip_limit.get()
        self.e_clip_limit = tk.Entry(threshold_container,textvariable=self.s_clip_limit,width=5)
        self.e_clip_limit.grid(row=1,column=7)

        self.b_clear_ranges = tk.ttk.Button(threshold_container,
                                    command=self.clear_threshold_ranges)
        self.b_clear_ranges.configure(text="Clear Ranges")
        self.b_clear_ranges.grid(row=1, column=8, sticky=W)

        self.b_check_threshold = tk.ttk.Button(threshold_container,
                                    command=self.check_threshold)
        self.b_check_threshold.configure(text="Check Threshold")
        self.b_check_threshold.grid(row=1, column=9, sticky=W)

        self.rectangles=[]
        self.rectangle = Rectangle(
                            xy=(int(self.s_threshold_lower.get()),0),
                            width=(int(self.s_threshold_lower.get())
                                 -int(self.s_threshold_upper.get())),
                            height=5000,
                            alpha=0.5,facecolor=(55/255,126/255,184/255),
                            edgecolor=None)
        self.threshold_ax[3].add_patch(self.rectangle)
        def onselect(xmin, xmax):
            rect = Rectangle(
                            xy=(xmin,0),width=(xmax-xmin),
                            height=self.threshold_ax[3].get_ylim()[1],
                            alpha=0.5,facecolor=(55/255,126/255,184/255),
                            edgecolor=None)

            if not self.bool_multi_ranges.get():
                # Remove old rectangles
                try:
                    self.rectangle.remove()
                except:
                    pass
                self.rectangle = rect
                self.s_threshold_lower.set(str(int(xmin)))
                self.s_threshold_upper.set(str(int(xmax)))
                self.threshold_ax[3].add_patch(self.rectangle)
            else:
                self.rectangles.append(rect)
                self.threshold_ax[3].add_patch(self.rectangles[-1])
                if self.s_threshold_lower.get()=='':
                    insert_string_1 = str(int(xmin))
                    insert_string_2 = str(int(xmax))
                else:
                    insert_string_1 = self.s_threshold_lower.get() + ',' + str(int(xmin))
                    insert_string_2 = self.s_threshold_upper.get() + ',' + str(int(xmax))
                self.s_threshold_lower.set(insert_string_1)
                self.s_threshold_upper.set(insert_string_2)

            # Make rectangle showing selected area
            #self.threshold_ax[3].add_patch(rect)
            self.check_threshold()

        # Span selector for threshold range
        self.span = SpanSelector(self.threshold_ax[3], onselect, 'horizontal', useblit=True,
                            rectprops=dict(alpha=0.5, facecolor=(55/255,126/255,184/255)))

        self.pack(fill=BOTH, expand=1)

    def get_directory_click(self):
        self.t_file_dir.delete("1.0",END)
        self.base_dir = askdirectory(initialdir=self.base_dir)
        self.t_file_dir.insert(INSERT, self.base_dir +'/')
    def pick_df(self):
        # Pick save dataframe
        self.df_file = askopenfilename(
                            initialdir=self.df_dir,
                            title='Choose DataFrame .pkl'
                            )
        #if self.df_file:
            #self.b_pick_df.configure(bg='green')
    def get_images_click(self):
        # Reset initialization for other functions
        self.crop_initialized = False
        self.threshold_initialized = False
        file_list=[]
        files = askopenfilenames(
                  initialdir=self.base_dir,title='Choose files',
                  filetypes=(("png files",".png"),
                            ("tiff files",".tiff"),
                            ("all files","*.*")))
        for file in files:
            file_list.append(file)
        self.time_files = file_list
        # Try to find magnification and other metadata
        base_file = os.path.basename(self.time_files[0])
        base_file = base_file.replace('-','_')
        splits = base_file.split('_')
        for split in splits:
            split2 = split.split('=')
            if 'mag' in split.lower():
                # looking for _mag=##x_ or _magnification=##x_
                self.s_mag.set(split2[1])
                print(self.s_mag.get())
            elif 'sub' in split.lower():
                # looking for _sub=*_ or _substrate=*_ in filename
                self.s_sample_props['substrate'].set(split2[1])
            elif any(x in split for x in ['Ta','Tanneal','T']):
                # looking for _T=*C_ or _Tanneal=*C_ or _Ta=*C_
                self.s_sample_props['anneal_temp_c'].set(split2[1][:-1])
            elif any(x in split for x in ['t','thick','thickness']) and 'nm' in split:
                # looking for _t=*nm_ or _thick=*nm_, etc.
                self.s_sample_props['thickness_nm'].set(split2[1][:-2])
            elif 'mat=' in split:
                self.s_sample_props['material'].set(split[4:])
            elif any(x in split for x in ['Td','Tgrowth','Tdep']):
                self.s_sample_props['deposition_temp_c'].set(split2[1][:-1])

        # Try to find growth date from folder (move up a level up to 4 times)
        split = os.path.split(self.base_dir)
        for i in range(4):
            if len(split[1].split('_')[0])==10 and all(split[1][idx].isnumeric for idx in [0,1,2,3,5,6,8,9]):
                self.s_sample_props['growth_date'].set(split[1].split('_')[0])
                break
            else:
                split = os.path.split(split[0])




    def pick_crop_region(self):
        # Zoom to region of interest in image. This will select crop region below
        # Pick the last time so the whole grain is contained within the crop region
        img=misc.imread(os.path.join(self.base_dir,self.time_files[-1]),
                      mode='L')
        #img = exposure.rescale_intensity(img,in_range='image')
        img = exposure.equalize_adapthist(img,clip_limit=0.05)
        #fig,self.crop_ax=plt.subplots()
        #self.crop_fig, self.crop_ax = plt.subplots()
        if not self.crop_initialized:
            self.cropData = self.ax[0].imshow(img)
            self.canvas.draw()
        else:
            # Remove old text, if exists
            try:
                for txt in self.line_texts:
                    txt.remove()
                self.line_texts=[]
                # remove old lines as well
                for line in self.ax[0].lines:
                    line.remove()
            except:
                pass
            # Set new data
            set_new_im_data(self.ax[0],self.cropData,img)
            self.canvas.draw()
        self.crop_initialized = True
        # Reset threshold
        self.threshold_initialized = False
        #plt.show()
        #self.canvas.draw()
    def get_axes_ranges(self):
        x1,x2=self.ax[0].get_xlim()
        y2,y1=self.ax[0].get_ylim()
        self.x1=int(x1)
        self.x2=int(x2)
        self.y2=int(y2)
        self.y1=int(y1)
        self.l_crop_range.config(text=('x1 = ' + str(self.x1) +
                                    ', x2 = ' + str(self.x2) +
                                    ', y1 = ' + str(self.y1) +
                                    ', y2 = ' + str(self.y2)))
        print(x1,x2,y1,y2)
    def eq_hist_cb_command(self):
        self.threshold_initialized=False
    def clear_threshold_ranges(self):
        # Remove all rectangles
        [p.remove() for p in reversed(self.rectangles)]
        self.rectangles=[]
        try:
            self.rectangle.remove()
        except:
            pass
        # Reset threshold variables
        self.s_threshold_lower.set('')
        self.s_threshold_upper.set('')
        self.threshold_canvas.draw()
    def check_threshold(self):
        if not self.s_clip_limit.get() == self.last_clip_limit:
            self.threshold_initialized=False
            [b.remove() for b in self.threshold_plot_data[3][2]]
        if not self.threshold_initialized:
            self.original_image=misc.imread(os.path.join(self.base_dir,
                                                  self.time_files[-1]),
                                      mode='L')
            try:
                [b.remove() for b in self.threshold_plot_data[3][2]]
            except:
                pass
        if self.bool_multi_ranges:
            threshold_lower = [float(x) for x in
                            self.s_threshold_lower.get().split(',')]
            threshold_upper = [float(x) for x in
                            self.s_threshold_upper.get().split(',')]
        else:
            threshold_lower = float(self.s_threshold_lower.get())
            threshold_upper = float(self.s_threshold_upper.get())
        denoised,thresholded,cropped = threshold_crop_denoise(
                                      self.time_files[-1],
                                      self.x1,self.x2,self.y1,self.y2,
                                      threshold_lower,
                                      threshold_upper,
                                      int(self.s_disk.get()),
                                      equalize_hist=self.bool_eq_hist.get(),
                                      multiple_ranges=self.bool_multi_ranges.get(),
                                      threshold_out=self.bool_threshold_out.get(),
                                      clip_limit=float(self.s_clip_limit.get())
                                      )

        if not self.threshold_initialized:
            self.threshold_plot_data = ['']*4
            self.threshold_plot_data[0] = self.threshold_ax[0].imshow(cropped,cmap=plt.get_cmap('gray'))
            self.threshold_plot_data[1] = self.threshold_ax[1].imshow(thresholded,cmap=plt.get_cmap('gray'))
            self.threshold_plot_data[2] = self.threshold_ax[2].imshow(denoised,cmap=plt.get_cmap('gray'))
            # Plot the histogram so we can select a good threshold for the grains
            self.threshold_plot_data[3]=self.threshold_ax[3].hist(
                    cropped.ravel(),bins=256,alpha=0.8,
                    color=(228/255,26/255,28/255))
            # Set subplot titles
            self.threshold_ax[0].set_title('Original Image')
            self.threshold_ax[2].set_title('Despeckled')
            self.threshold_ax[3].set_title('Click and Drag \n to Select Threshold')
        elif self.threshold_initialized:
            set_new_im_data(self.threshold_ax[1],self.threshold_plot_data[1],thresholded)
            set_new_im_data(self.threshold_ax[2],self.threshold_plot_data[2],denoised)
        self.threshold_ax[1].set_title('Thresholded Between \n' + self.s_threshold_lower.get() + ' and ' + self.s_threshold_upper.get())
        self.threshold_canvas.draw()
        self.threshold_initialized = True
        self.last_clip_limit=self.s_clip_limit.get()

    def draw_line_segments(self):
        if self.bool_multi_ranges:
            threshold_lower = [float(x) for x in
                            self.s_threshold_lower.get().split(',')]
            threshold_upper = [float(x) for x in
                            self.s_threshold_upper.get().split(',')]
        else:
            threshold_lower = float(self.s_threshold_lower.get())
            threshold_upper = float(self.s_threshold_upper.get())
        denoised = threshold_crop_denoise(
                                      self.time_files[-1],
                                      self.x1,self.x2,self.y1,self.y2,
                                      threshold_lower,
                                      threshold_upper,
                                      int(self.s_disk.get()),
                                      equalize_hist=self.bool_eq_hist.get(),
                                      multiple_ranges=self.bool_multi_ranges.get(),
                                      threshold_out=self.bool_threshold_out.get(),
                                      clip_limit=float(self.s_clip_limit.get())
                                      )[0]
        # Remove old lines
        for line in self.ax[0].lines:
            line.remove()
        # Remove old text, if exists
        try:
            for txt in self.line_texts:
                txt.remove()
            self.line_texts=[]
        except:
            pass
        self.ax[0].set_title('click to build line segments')
        # Change data extent to match new cropped image
        self.cropData.set_extent((0, denoised.shape[1], denoised.shape[0], 0))
        # Reset axes limits
        self.ax[0].set_xlim(0,denoised.shape[1])
        self.ax[0].set_ylim(denoised.shape[0],0)
        # Now set the data
        self.cropData.set_data(denoised)
        self.ax[0].relim()
        #self.ax[0].imshow(denoised)
        # Alternatively
        #img=misc.imread(os.path.join(self.base_dir,self.time_files[-1]),mode='L')
        # ax.imshow(img[self.y1:self.y2,self.x1:self.x2])
        line, = self.ax[0].plot([], [],'-or')  # empty line
        self.linebuilder = LineBuilder(line)
        #self.ax[0].axis('off')

        self.canvas.draw()
    def get_line_segments(self):
        # Get line coordinates
        # One line drawn
        self.lines=[]
        if len(self.linebuilder.xs)==2:
            linex1,linex2 = self.linebuilder.xs
            liney1,liney2 = self.linebuilder.ys
            self.lines.append([(linex1,liney1),(linex2,liney2)])
        # Multiple lines drawn
        elif len(self.linebuilder.xs)%2<0.1:
            for i in np.arange(0,len(self.linebuilder.xs),2):
                linex1,linex2 = self.linebuilder.xs[i:i+2]
                liney1,liney2 = self.linebuilder.ys[i:i+2]
                self.lines.append([(linex1,liney1),(linex2,liney2)])
        # Incorrect number of points
        elif len(self.linebuilder.xs)%2==1:
            print('Incorrect number of points, draw start and endpoint for each direction of interest')
        print(self.lines)
    def check_edge_detection(self):
        # Remove old lines
        for line in self.ax[1].lines:
            line.remove()
        img=misc.imread(os.path.join(self.base_dir,self.time_files[-1]),mode='L')
        #ax[0].imshow(img)
        if self.bool_multi_ranges:
            threshold_lower = [float(x) for x in
                            self.s_threshold_lower.get().split(',')]
            threshold_upper = [float(x) for x in
                            self.s_threshold_upper.get().split(',')]
        else:
            threshold_lower = float(self.s_threshold_lower.get())
            threshold_upper = float(self.s_threshold_upper.get())
        denoised = threshold_crop_denoise(
                                      self.time_files[-1],
                                      self.x1,self.x2,self.y1,self.y2,
                                      threshold_lower,
                                      threshold_upper,
                                      int(self.s_disk.get()),
                                      equalize_hist=self.bool_eq_hist.get(),
                                      multiple_ranges=self.bool_multi_ranges.get(),
                                      threshold_out=self.bool_threshold_out.get(),
                                      clip_limit=float(self.s_clip_limit.get())
                                      )[0]
        # Get edge of growth front from image profile
        line = self.lines[0]
        profile = profile_line(denoised,
                            (line[0][1],line[0][0]),
                            (line[1][1],line[1][0]))
        self.ax[1].plot(profile)
        # Find last point on grain (where image is saturated)
        last_idx = np.where(profile>255*.5)[0][-1]
        self.ax[1].plot(last_idx,255,'o')
        
        theta = np.arctan2((line[1][1]-line[0][1]),(line[1][0]-line[0][0]))
        total_length = np.sqrt((line[1][1]-line[0][1])**2 + (line[1][0]-line[0][0])**2)
        x_edge = line[0][0] + np.cos(theta)*((last_idx+1)/profile.shape[0])*total_length
        y_edge = line[0][1] + np.sin(theta)*((last_idx+1)/profile.shape[0])*total_length
        #self.ax[0].plot(line[0][0],line[0][1],'ob')
        #self.ax[0].plot(line[1][0],line[1][1],'ob')
        self.ax[0].plot(x_edge,y_edge,'ob')
        self.canvas.draw()

    def extract_growth_rates(self):
        if self.s_time_source.get()=='Date Modified':
            # Get time from last modified time
            t0 = datetime.datetime.fromtimestamp(os.path.getmtime(self.time_files[0]))
            self.times=[0]*len(self.time_files)
            for idx,timeFile in enumerate(self.time_files):
                ti = datetime.datetime.fromtimestamp(os.path.getmtime(self.time_files[idx]))
                self.times[idx] = (ti-t0).total_seconds()
        elif self.s_time_source.get()=='Filename (time=*s)':
            # Get time from filename'
            self.times=[0]*len(self.time_files)
            for idx,timeFile in enumerate(self.time_files):
                # Split first by "time=" then by "s" to get the numbers in between
                self.times[idx] = float((timeFile.split('time=')[1]).split('s')[0])
                #self.times[idx] = float((timeFile.split('t=')[1]).split('.png')[0])
                
        # Check if images dimensions are as expected. If not use image width
        # Not very robust yet
        img = misc.imread(self.time_files[-1],mode='L')
        if img.shape[1]==2048:
            length_per_pixel = micron_per_pixel[self.s_mag.get()]
        else:
            length_per_pixel = image_width_microns[self.s_mag.get()]/img.shape[1]
        # Remove old data
        self.ax[1].clear()
        # Loop through files
        filesToPlot = self.time_files
        time_list = self.times
        sort_indices = sorted(range(len(time_list)), key=lambda k: time_list[k])
        self.distances = np.zeros((len(self.lines),len(sort_indices)))
        if self.bool_multi_ranges:
            threshold_lower = [float(x) for x in
                            self.s_threshold_lower.get().split(',')]
            threshold_upper = [float(x) for x in
                            self.s_threshold_upper.get().split(',')]
        else:
            threshold_lower = float(self.s_threshold_lower.get())
            threshold_upper = float(self.s_threshold_upper.get())

        for idx,sort_idx in enumerate(sort_indices):
            timeFile = filesToPlot[sort_idx]
            if idx==0:
                t0=self.times[sort_idx]
                ti=0
            else:
                ti = self.times[sort_idx]-t0
            denoised = threshold_crop_denoise(self.time_files[sort_idx],
                                          self.x1,self.x2,self.y1,self.y2,
                                          threshold_lower,
                                          threshold_upper,
                                          int(self.s_disk.get()),
                                          equalize_hist=self.bool_eq_hist.get(),
                                          multiple_ranges=self.bool_multi_ranges.get(),
                                          threshold_out=self.bool_threshold_out.get(),
                                          clip_limit=float(self.s_clip_limit.get())
                                          )[0]
            for idx2 in range(0,len(self.lines)):
                self.distances[idx2][idx] = get_growth_edge(
                    denoised,self.lines[idx2],
                    length_per_pixel=length_per_pixel
                    )
        self.growth_rates=[]
        self.growth_rates_string=[]
        for idx,line in enumerate(self.lines):
            filterIdx = np.where(self.distances[idx]>0)[0]
            self.times = np.array(self.times)
            # Fit the data with a line
            params = np.polyfit(self.times[filterIdx], self.distances[idx][filterIdx], 1)
            self.ax[1].plot(self.times,np.array(self.times)*params[0]+params[1],'--k',linewidth=1.5)
            self.ax[1].set_xlabel('Time (s)')
            self.ax[1].set_ylabel('Grain Radius ($\mu$m)')
            print('{:.2f}'.format(params[0])+' micron/sec')
            self.growth_rates_string.append('{:.2f}'.format(params[0])+' micron/sec')
            self.growth_rates.append(params[0])
            self.ax[1].plot(self.times,self.distances[idx],'o',label='#' + str(idx+1) + ', ' + '{:.2f}'.format(params[0])+' $\mu$m/s')
        self.legend = self.ax[1].legend(bbox_to_anchor=(1.0, 1.0))
        # Re-evaluate limits
        self.ax[1].relim()
        self.canvas.draw()
        self.label_lines()

    def save_results(self):
        # Make save directory
        self.save_dir = os.path.join(self.base_dir,'analysis_results')
        if not os.path.isdir(self.save_dir):
            os.mkdir(self.save_dir)
        # Save growth rate file
        # header = 'time(s),'
        # for i in range(1,self.distances.shape[0]+1):
            # header += 'line#'+str(i)+'(micron)'
            # if not i == self.distances.shape[0]:
                # header += ','
            # else:
                # header += '\n'
        # for i,growth_rate in enumerate(self.growth_rates_string):
            # header += growth_rate
            # if not i == len(self.growth_rates_string):
                # header += ','
        # savename = self.increment_save_name(self.save_dir,'radius_vs_time','.csv')
        # np.savetxt(os.path.join(self.save_dir,savename+'.csv'),np.transpose(np.insert(self.distances,0,self.times,axis=0)),
                    # delimiter=',',header=header)
        # savename = self.increment_save_name(self.save_dir,'growthrates','.csv')
        # with open(os.path.join(self.save_dir,savename+'.csv'), 'a') as f:
            # f.write('Line#,Growth Rate (micron/sec) \n')
            # for idx,growthRate in enumerate(self.growth_rates):
                # line = str(idx+1) + ',' + str(growthRate) + '\n'
                # f.write(line)
        # Save figures
        savename = self.increment_save_name(self.save_dir,'growth_rates_plot','.png')
        self.fig.savefig(os.path.join(self.save_dir,savename+'.png'),dpi=200,bbox_inches='tight')
        savename = self.increment_save_name(self.save_dir,'threshold_plot','.png')
        self.threshold_fig.savefig(os.path.join(self.save_dir,savename+'.png'),dpi=200,bbox_inches='tight')
        # Save dataframe
        # If no file was selected make new filename and df
        if not self.df_file:
            self.df_file = (self.increment_save_name(
                self.df_dir,str(datetime.date.today()) + '_df','.pkl')
                +'.pkl'
                )
            self.df = pd.DataFrame()
        # otherwise, load df
        else:
            self.df = pd.read_pickle(os.path.join(self.df_dir,self.df_file))
        # Now append data
        data_dict_list=[]
        for line_idx,growth_rate in enumerate(self.growth_rates):
            temp_dict = {'growth_rate_umps':growth_rate,
                        'line':self.lines[line_idx],
                        'x1,x2,y1,y2':(self.x1,self.x2,self.y1,self.y2),
                        'image_files':[os.path.basename(x) for x in self.time_files],
                        'image_dir':os.path.split(self.time_files[0])[0],
                        'threshold_lower':float(self.s_threshold_lower.get()),
                        'threshold_upper':float(self.s_threshold_upper.get()),
                        'disk':int(self.s_disk.get()),
                        'histogram_equalization':self.bool_eq_hist.get()}
            for key,input_dict in self.sample_props.items():
                if input_dict['dtype']=='string':
                    temp_string = self.s_sample_props[key].get()
                    if '/' in temp_string:
                        temp_list = []
                        for substring in temp_string.split('/'):
                            temp_list.append(substring)
                        temp_dict[key]=temp_list
                    else:
                        temp_dict[key]=temp_string
                elif input_dict['dtype']=='float':
                    # Try separating by '/' for layer stacks
                    temp_string = self.s_sample_props[key].get()
                    if '/' in temp_string:
                        temp_list = []
                        for sublayer in temp_string.split('/'):
                            temp_list.append(float(sublayer))
                        temp_dict[key]=temp_list
                    else:
                        temp_dict[key]=float(self.s_sample_props[key].get())
            data_dict_list.append(temp_dict)
        #print(data_dict_list)
        self.df = self.df.append(data_dict_list,ignore_index=True)
        #print(self.df)
        # Pickle the dataframe
        self.df.to_pickle(os.path.join(self.df_dir,self.df_file))
        # Save csv of data
        savename = self.increment_save_name(self.save_dir,'growth_rates_data','.csv')
        pd.DataFrame(data_dict_list).to_csv(os.path.join(self.save_dir,savename))

    def increment_save_name(self,path,savename,extension):
        name_hold = savename
        if name_hold.endswith(extension):
            name_hold = name_hold.rstrip(extension)
        if os.path.isfile(os.path.join(path,name_hold+extension)):
            for add_i in range(1,10):
                name_temp = name_hold + '_' + str(add_i)
                if not os.path.isfile(os.path.join(path,name_temp + extension)):
                    name_hold = name_temp
                    break
        return name_hold

    def label_lines(self):
        # Remove old text, if exists
        try:
            for txt in self.line_texts:
                txt.remove()
            self.line_texts=[]
        except:
            pass
        for line in self.ax[0].lines:
            line.remove()
        img=misc.imread(os.path.join(self.base_dir,self.time_files[-1]))#,mode='L')
        img = exposure.equalize_adapthist(img,clip_limit=0.05)
        self.cropData.set_data(img[self.y1:self.y2,self.x1:self.x2])
        line, = self.ax[0].plot([], [], '-or')
        # Draw lines on image
        line.set_data(self.linebuilder.xs, self.linebuilder.ys)
        keyStr = '' #string to display growth rates
        self.line_texts=[]
        for idx in range(0, len(self.lines)):    #add labels to lines
            txt = self.ax[0].text(self.lines[idx][1][0],
                                self.lines[idx][1][1]-25,
                                idx+1, color = 'red',
                                size = 'x-large', weight = 'bold')
            self.line_texts.append(txt)
            keyStr = keyStr + str(idx+1) + ': ' + str(self.growth_rates_string[idx]) #add growth rate to keyStr
            if idx != len(self.lines)-1:
                keyStr = keyStr + '\n'
        #self.ax[0].text(1.05, 0.5, keyStr, transform=self.ax[0].transAxes, size = 'x-large', bbox=dict(facecolor='white', alpha=1))
        self.ax[0].axis('off')
        self.ax[0].set_title('')
        self.ax[0].relim()
        # Store the figure so it can be saved later
        self.labeledLinesFig = plt.gcf()
        self.canvas.draw()


# Interactively draw line
# You can draw multiple lines as well
class LineBuilder:
    def __init__(self, line):
        self.line = line
        self.xs = list(line.get_xdata())
        self.ys = list(line.get_ydata())
        self.cid = line.figure.canvas.mpl_connect('button_press_event', self)

    def __call__(self, event):
        print('click', event)
        if event.inaxes!=self.line.axes: return
        #first click sets values of nucleation site, creates point at n-site
        if len(self.xs) == 0:
            self.x1 = event.xdata
            self.y1 = event.ydata
            self.xs.append(self.x1)
            self.ys.append(self.y1)
        #second click connects n-site to click point
        elif len(self.xs) == 1:
            self.xs.append(event.xdata)
            self.ys.append(event.ydata)
        #following clicks each create a line from n-site to click point
        else:
            self.xs.append(self.x1)
            self.ys.append(self.y1)
            self.xs.append(event.xdata)
            self.ys.append(event.ydata)


        self.line.set_data(self.xs, self.ys)
        self.line.figure.canvas.draw()


def main():
    root = tk.Tk()
    app = GrowthRateAnalyzer(root)
    root.mainloop()
    #app.arduino.close()

if __name__ == '__main__':
    main()