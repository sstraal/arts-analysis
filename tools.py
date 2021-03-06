import numpy as np
import glob
import scipy.signal

# should there maybe be a clustering class
# and a S/N calculation class?

class AnalyseTriggers:

    def __init__(self):
        pass 

def combine_all_beams(fdir, fnout=None):

    flist = glob.glob(fdir+'/CB*.cand')

    data_all = []

    for fn in flist:
        print(fn)
        try:
            CB = float(fn.split('CB')[-1][:2])
        except:
            continue

        data = np.genfromtxt(fn)

        if len(data)<1:
            continue

        beamno = np.ones([len(data)])*CB
        data_full = np.concatenate([data, beamno[:, None]], axis=-1)
        data_all.append(data_full)

    data_all = np.concatenate(data_all)
    if type(fnout) is str:
        np.savetxt(fnout, data_all)

    return data_all

def dm_range(dm_max, dm_min=5., frac=0.2):
    """ Generate list of DM-windows in which 
    to search for single pulse groups. 

    Parameters
    ----------
    dm_max : float 
        max DM 
    dm_min : float  
        min DM 
    frac : float 
        fractional size of each window 

    Returns
    -------
    dm_list : list 
        list of tuples containing (min, max) of each 
        DM window
    """

    dm_list =[]
    prefac = (1-frac)/(1+frac)

    while dm_max>dm_min:
        if dm_max < 100.:
            prefac = (1-2*frac)/(1+2*frac)
        if dm_max < 50.:
            prefac = 0.0 

        dm_list.append((int(prefac*dm_max), int(dm_max)))
        dm_max = int(prefac*dm_max)

    return dm_list

def read_singlepulse(fn, max_rows=None):
    """ Read in text file containing single-pulse 
    candidates. Allowed formats are:
    .singlepulse = PRESTO output
    .txt = injection pipeline output
    .trigger = AMBER output 
    .cand = heimdall output 

    max_rows sets the maximum number of 
    rows to read from textfile 
    """

    if fn.split('.')[-1] in ('singlepulse', 'txt'):
        A = np.genfromtxt(fn, max_rows=max_rows)
        dm, sig, tt, downsample = A[:,0], A[:,1], A[:,2], A[:,4]
    elif fn.split('.')[-1]=='trigger':
        A = np.genfromtxt(fn, max_rows=max_rows)
        # Check if amber has compacted, in which case 
        # there are two extra rows
        if len(A[0]) > 7: 
            # beam batch sample integration_step compacted_integration_steps time DM compacted_DMs SNR
            dm, sig, tt, downsample = A[:,-3], A[:,-1], A[:, -4], A[:, 3]
        else:
            # beam batch sample integration_step time DM SNR
            dm, sig, tt, downsample = A[:,-2], A[:,-1], A[:, -3], A[:, 3]
    elif fn.split('.')[-1]=='cand':
        A = np.genfromtxt(fn, max_rows=max_rows)
        # SNR sample_no time log_2_width DM_trial DM Members first_samp last_samp
        dm, sig, tt, log_2_downsample = A[:,5], A[:,0], A[:, 2], A[:, 3]
        downsample = 2**log_2_downsample
        try:
            beamno = A[:, 9]
            return dm, sig, tt, downsample, beamno
        except:
            pass
    else:
        print("Didn't recognize singlepulse file")
        return 

    if len(A)==0:
        return 0, 0, 0, 0

    return dm, sig, tt, downsample

def get_triggers(fn, sig_thresh=5.0, dm_min=0, dm_max=np.inf, 
                 t_window=0.5, max_rows=None):
    """ Get brightest trigger in each 10s chunk.

    Parameters
    ----------
    fn : str 
        filename with triggers (.npy, .singlepulse, .trigger)
    sig_thresh : float
        min S/N to include
    t_window : float 
        Size of each time window in seconds

    Returns
    -------
    sig_cut : ndarray
        S/N array of brightest trigger in each DM/T window 
    dm_cut : ndarray
        DMs of brightest trigger in each DM/T window 
    tt_cut : ndarray
        Arrival times of brightest trigger in each DM/T window 
    ds_cut : ndarray 
        downsample factor array of brightest trigger in each DM/T window 
    """

    dm, sig, tt, downsample = read_singlepulse(fn, max_rows=max_rows)[:4]
    ntrig_orig = len(dm)

    low_sig_ind = np.where(sig < sig_thresh)[0]
    sig = np.delete(sig, low_sig_ind)
    tt = np.delete(tt, low_sig_ind)
    dm = np.delete(dm, low_sig_ind)
    downsample = np.delete(downsample, low_sig_ind)

    sig_cut, dm_cut, tt_cut, ds_cut = [],[],[],[]
    
    tduration = tt.max() - tt.min()
    ntime = int(tduration / t_window)

    # Make dm windows between 90% of the lowest trigger and 
    # 10% of the largest trigger
    if dm_min==0:
        dm_min = 0.9*dm.min()
    if dm_max > 1.1*dm.max():
        dm_max = 1.1*dm.max()

    # Can either do the DM selection here, or after the loop
#    dm_list = dm_range(dm_max, dm_min=dm_min)
    dm_list = dm_range(1.1*dm.max(), dm_min=0.9*dm.min())

    print("\nGrouping in window of %.2f sec" % np.round(t_window,2))
    print("DMs:", dm_list)

    tt_start = tt.min() - .5*t_window
    ind_full = []

    # might wanna make this a search in (dm,t,width) cubes
    for dms in dm_list:
        for ii in xrange(ntime + 2):
            try:    
                # step through windows of t_window seconds, starting from tt.min()
                # and find max S/N trigger in each DM/time box
                t0, tm = t_window*ii + tt_start, t_window*(ii+1) + tt_start
                ind = np.where((dm<dms[1]) & (dm>dms[0]) & (tt<tm) & (tt>t0))[0] 
                ind_maxsnr = ind[np.argmax(sig[ind])]
                sig_cut.append(sig[ind_maxsnr])
                dm_cut.append(dm[ind_maxsnr])
                tt_cut.append(tt[ind_maxsnr])
                ds_cut.append(downsample[ind_maxsnr])
                ind_full.append(ind_maxsnr)
            except:
                continue

    ind_full = np.array(ind_full)
    dm_cut = np.array(dm_cut)
    # now remove the low DM candidates
    ind = np.where((dm_cut >= dm_min) & (dm_cut <= dm_max))[0]

    dm_cut = dm_cut[ind]
    ind_full = ind_full[ind]
    sig_cut = np.array(sig_cut)[ind]
    tt_cut = np.array(tt_cut)[ind]
    ds_cut = np.array(ds_cut)[ind]

    ntrig_group = len(dm_cut)

    print("Grouped down to %d triggers from %d\n" % (ntrig_group, ntrig_orig))

    return sig_cut, dm_cut, tt_cut, ds_cut, ind_full

class SNR_Tools:

    def __init__(self):
        pass

    def sigma_from_mad(self, data):
        """ Get gaussian std from median 
        aboslute deviation (MAD)
        """
        assert len(data.shape)==1, 'data should be one dimensional'

        med = np.median(data)
        mad = np.median(np.absolute(data - med))

        return 1.4826*mad, med

    def calc_snr(self, data):
        """ Calculate S/N of 1D input array (data)
        after excluding 0.05 at tails
        """
        std_chunk = scipy.signal.detrend(data, type='linear')
        std_chunk.sort()
        ntime_r = len(std_chunk)
        stds = 1.148*np.sqrt((std_chunk[ntime_r//40:-ntime_r//40]**2.0).sum() /
                              (0.95*ntime_r))
        snr_ = std_chunk[-1] / stds 

        return snr_

    def calc_snr_widths(self, data, widths=None):
        """ Calculate the S/N of pulse profile after 
        trying 9 rebinnings.

        Parameters
        ----------
        arr   : np.array
            (ntime,) vector of pulse profile 

        Returns
        -------
        snr : np.float 
            S/N of pulse
        """
        assert len(data.shape)==1
        
        ntime = len(data)
        snr_max = 0
        data -= np.median(data)

        if widths is None:
            widths = [1, 2, 4, 8, 16, 32, 64, 128]

    #    for ii in range(1, 10):
        for ii in widths:
            for jj in range(ii):
                # skip if boxcar width is greater than 1/4th ntime
                if ii > ntime//8:
                    continue
                
                arr_copy = data.copy()
                arr_copy = np.roll(arr_copy, jj)
                arr_ = arr_copy[:ntime//ii*ii].reshape(-1, ii).mean(-1)

                snr_ = self.calc_snr(arr_)

                if snr_ > snr_max:
                    snr_max = snr_
                    width_max = ii

        return snr_max, width_max

    def compare_snr(self, fn_1, fn_2, dm_min=0, dm_max=np.inf, save_data=False,
                    sig_thresh=5.0, t_window=0.5, max_rows=None):
        """ Read in two files with single-pulse candidates
        and compare triggers.

        Parameters:
        ----------
        fn_1 : str 
            name of input triggers text file
            (must be .trigger, .singlepulse, or .txt)
        fn_2 : str
            name of input triggers text file for comparison 
        dm_min : float
            do not process triggers below this DM 
        dm_max : float 
            do not process triggers above this DM 
        save_data : bool 
            if True save to np.array
        sig_thresh : float 
            do not process triggers below this S/N 
        t_window : float 
            time window within which triggers in 
            fn_1 and fn_2 will be considered the same 

        Return:
        -------
        Function returns four parameter arrays for 
        each fn_1 and fn_2, which should be ordered so 
        that they can be compared directly:

        grouped_params1, grouped_params2, matched_params
        """
        snr_1, dm_1, t_1, w_1, ind_full_1 = get_triggers(fn_1, sig_thresh=sig_thresh, 
                                    dm_min=dm_min, dm_max=np.inf, t_window=t_window, 
                                    max_rows=max_rows)

        snr_2, dm_2, t_2, w_2, ind_full_2 = get_triggers(fn_2, sig_thresh=sig_thresh, 
                                    dm_min=dm_min, dm_max=dm_max, t_window=t_window, 
                                    max_rows=max_rows)

        snr_2_reorder = []
        dm_2_reorder = []
        t_2_reorder = []
        w_2_reorder = []

        ntrig_1 = len(snr_1)
        ntrig_2 = len(snr_2)    

        par_1 = np.concatenate([snr_1, dm_1, t_1, w_1]).reshape(4, -1)
        par_2 = np.concatenate([snr_2, dm_2, t_2, w_2]).reshape(4, -1)

        # Make arrays for the matching parameters
        par_match_arr = []
        ind_missed = []

        print("t_diff   t_0   t_1   dm_0   dm_1  snr_1   snr_2")
        for ii in range(len(snr_1)):
            tdiff = np.abs(t_1[ii] - t_2)
            ind = np.where(tdiff == tdiff.min())[0]

            # make sure you are getting correct trigger in dm/time space
            if len(ind) > 1:
                ind = ind[np.argmin(np.abs(dm_1[ii]-dm_2[ind]))]
            else:
                ind = ind[0]

            # check for triggers that are within 1.0 seconds and 20% in dm
            if (tdiff[ind]<1.0) and (np.abs(dm_1[ii]-dm_2[ind])/dm_1[ii])<0.2:
                pparams = (tdiff[ind], t_1[ii], t_2[ind], dm_1[ii], dm_2[ind], snr_1[ii], snr_2[ind], w_1[ii], w_2[ind])
                print("%1.4f  %5.1f  %5.1f  %5.1f  %5.1f %5.1f  %5.1f %5.1f  %5.1f" % pparams)

                params_match = np.array([snr_1[ii], snr_2[ind], 
                                         dm_1[ii], dm_2[ind],
                                         t_1[ii], t_2[ind],
                                         w_1[ii], w_2[ind]])

                par_match_arr.append(params_match)
            else:
                # Keep track of missed triggers
                ind_missed.append(ii)

        if len(par_match_arr)==0:
            print("No matches found")
            return 

        # concatenate list and reshape to (nparam, nmatch, 2 files)
        par_match_arr = np.concatenate(par_match_arr).reshape(-1, 4, 2)
        par_match_arr = par_match_arr.transpose((1, 0, 2))

        if save_data is True:
            nsnr = min(len(snr_1), len(snr_2))
            snr_1 = snr_1[:nsnr]
            snr_2 = snr_2_reorder[:nsnr]

            np.save(fn_1+'_params_grouped', par_1)
            np.save(fn_2+'_params_grouped', par_2)
            np.save('params_matched', par_match_1)

        return par_1, par_2, par_match_arr, ind_missed    

    def plot_comparison(self, par_1, par_2, par_match_arr, ind_missed, figname='./test.pdf'):
        fig = plt.figure(figsize=(12,12))

        frac_recovered = len(ind_missed)

        snr_1, snr_2 = par_1[0], par_2[0]
        dm_1, dm_2 = par_1[1], par_2[1]
        width_1, width_2 = par_1[3], par_2[3]

        snr_1_match = par_match_arr[0,:,0]
        snr_2_match = par_match_arr[0,:,1]

        dm_1_match = par_match_arr[1,:,0]
        dm_2_match = par_match_arr[1,:,1]

        width_1_match = par_match_arr[3,:,0]
        width_2_match = par_match_arr[3,:,1]

        fig.add_subplot(311)
        plt.plot(snr_1_match, snr_2_match, '.')
        plt.plot(snr_1, snr_1, color='k')
        plt.plot(snr_1[ind_missed], np.zeros([len(ind_missed)]), 'o', color='orange')
        plt.xlabel('Injected S/N', fontsize=15)
        plt.ylabel('Detected S/N', fontsize=15)        
        plt.legend(['Detected events','Expected S/N','Missed events'], fontsize=15)

        fig.add_subplot(312)
        plt.plot(dm_1_match, snr_1_match/snr_2_match, '.')
        plt.plot(dm_1[ind_missed], np.zeros([len(ind_missed)]), 'o', color='orange')
        plt.xlabel('DM', fontsize=15)
        plt.ylabel('Expected S/N : Detected S/N', fontsize=15)        
        plt.legend(['Detected events','Missed events'], fontsize=15)

        fig.add_subplot(337)
        plt.hist(width_1, bins=50, alpha=0.3, normed=True)
        plt.hist(width_2, bins=50, alpha=0.3, normed=True)
        plt.hist(width_1[ind_missed], bins=50, alpha=0.3, normed=True)
        plt.xlabel('Width [samples]', fontsize=15)

        fig.add_subplot(338)
        plt.plot(width_1_match, snr_1_match,'.')
        plt.plot(width_1_match, snr_2_match,'.')
        plt.plot(width_1, snr_1, '.')
        plt.xlabel('Width [samples]', fontsize=15)
        plt.ylabel('S/N injected', fontsize=15)

        fig.add_subplot(339)
        plt.plot(width_1_match, dm_1_match,'.')
        plt.plot(width_1_match, dm_2_match,'.')
        plt.plot(width_1, dm_1,'.')
        plt.xlabel('Width [samples]', fontsize=15)
        plt.ylabel('DM', fontsize=15)

        plt.tight_layout()
        plt.show()
        plt.savefig(figname)


if __name__=='__main__':

    import sys

    if len(sys.argv)<3:
        print("Too few arguments, expected: ")
        print("trigger_file_1 trigger_file_2 <dm_min> <dm_max>")

    fn_1, fn_2 = sys.argv[1], sys.argv[2]

    try:
        dm_min = np.float(sys.argv[3])
    except:
        dm_min = 0.0

    try:
        dm_max = np.float(sys.argv[4])
    except:
        dm_max = np.inf

    try:
        figname = sys.argv[5]
    except:
        figname = 'test.pdf'

    SNRTools = SNR_Tools()

    try:
        par_1, par_2, par_match_arr, ind_missed = SNRTools.compare_snr(fn_1, fn_2, dm_min=dm_min, 
                                        dm_max=dm_max, save_data=False,
                                        sig_thresh=5.0, t_window=0.1, max_rows=None)
    except TypeError:
        print("No matches, exiting")
        exit()
        

    print('\nFound %d common trigger(s)' % par_match_arr.shape[1])

    snr_1 = par_match_arr[0, :, 0]
    snr_2 = par_match_arr[0, :, 1]

    print(snr_1)
    print(snr_2)

    print('File 1 has %f times higher S/N than file 2' % np.mean(snr_1/snr_2))

    mk_plot = True

    if mk_plot is True:
        import matplotlib.pyplot as plt
        SNRTools.plot_comparison(par_1, par_2, par_match_arr, ind_missed, figname=figname)

