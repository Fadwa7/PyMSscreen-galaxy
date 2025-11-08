import axios from 'axios';

const API_BASE = process.env.REACT_APP_API_BASE || 'http://localhost:5000';

export const saveState = (state) => {
  return axios.post(`${API_BASE}/save_state`, state);
};

export const loadState = (payload) => {
  return axios.post(`${API_BASE}/load_state`, payload);
};

export const generateTable = (payload) => {
  return axios.post(`${API_BASE}/generate_table`, payload, {
    headers: {
      'Content-Type': 'application/json',
    }
  });
};

export const saveExtractConfig = async (config) => {
  return axios.post(`${API_BASE}/save_extract_config`, config);
};

export const loadExtractionConfig = async (workingDir) => {
  try {
    const params = new URLSearchParams({ working_directory: workingDir });
    const res = await axios.get(`${API_BASE}/load_extraction_config`, { params });
    return parseFloat(res.data.ret_time_shift_tol) || 0.5;
  } catch {
    return 0.5;
  }
};

// kick off background extract+prescreen; backend returns { job_id }
export const startExtractPrescreen = (working_directory) => {
  return axios.post(`${API_BASE}/start_extract_prescreen`, { working_directory });
};

// poll job status; backend returns { state, progress, message, done, error }
export const getJobStatus = (job_id) => {
  return axios.get(`${API_BASE}/job_status`, { params: { job_id } });
};

// (optional) cancel a running job
export const cancelJob = (job_id) => {
  return axios.post(`${API_BASE}/cancel_job`, { job_id });
};

export const extractData = (payload) => {
  return axios.post(`${API_BASE}/extract_data`, payload, {
    headers: {
      'Content-Type': 'application/json',
    }
  });
};

export const prescreenData = (payload) => {
  return axios.post(`${API_BASE}/prescreen_data`, payload, {
    headers: {
      'Content-Type': 'application/json',
    }
  });
};

export const loadComprehensiveTable = async (workingDirectory) => {
  return axios.get(`${API_BASE}/load_comprehensive_table`, {
    params: { working_directory: workingDirectory }
  });
};

export const exportSummaryPDF = async (compounds, working_directory) => {
  // Properly structure payload for backend
  const payload = {
    working_directory,
    compound_groups: compounds.reduce((groups, compound) => {
      const group = groups.find(g => g.group_name === compound.ID);
      if (group) {
        group.compounds.push(compound);
      } else {
        groups.push({
          group_name: compound.ID,
          compounds: [compound]
        });
      }
      return groups;
    }, [])
  };

  try {
    const response = await axios.post(`${API_BASE}/export_summary_pdf`, payload, {
      responseType: 'blob'
    });
    return response.data;
  } catch (error) {
    console.error('PDF export failed:', error);
    throw new Error('PDF export failed');
  }
};

export const saveQAFlags = (working_directory, flags) => {
  return axios.post(`${API_BASE}/save_qa_flags`, {
    working_directory,
    flags
  });
};
