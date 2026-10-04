// Thin promise wrappers around uni.request, shared by the chat and settings pages.
// The H5 dev server proxies /api to the FastAPI backend (see vite.config.js).

function request(method, url, data) {
  return new Promise((resolve, reject) => {
    uni.request({
      url,
      method,
      data,
      header: { 'Content-Type': 'application/json' },
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data)
          return
        }
        const detail = res.data && res.data.detail
        const message = typeof detail === 'string'
          ? detail
          : (detail && detail.detail) || `请求失败 (${res.statusCode})`
        reject(new Error(message))
      },
      fail: (err) => reject(err),
    })
  })
}

export const apiGet = (url) => request('GET', url)
export const apiPost = (url, data) => request('POST', url, data)
export const apiPut = (url, data) => request('PUT', url, data)
export const apiPatch = (url, data) => request('PATCH', url, data)
export const apiDelete = (url) => request('DELETE', url)

// Multipart upload (used by the knowledge-base file button).
export function apiUploadFile({ url, filePath, name, formData }) {
  return new Promise((resolve, reject) => {
    uni.uploadFile({
      url,
      filePath,
      name,
      formData,
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          try {
            resolve(JSON.parse(res.data))
          } catch (e) {
            resolve(res.data)
          }
          return
        }
        let message = `上传失败 (${res.statusCode})`
        try {
          const body = JSON.parse(res.data)
          const detail = body && body.detail
          message = typeof detail === 'string' ? detail : (detail && detail.detail) || message
        } catch (e) {
          /* keep the default message */
        }
        reject(new Error(message))
      },
      fail: reject,
    })
  })
}
