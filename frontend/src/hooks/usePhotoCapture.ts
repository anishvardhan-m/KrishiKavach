// Photo capture hook — handles camera/file input and resolves to a File object.

import { useCallback, useRef, useState } from "react"

export function usePhotoCapture() {
  const cameraInputRef = useRef<HTMLInputElement | null>(null)
  const galleryInputRef = useRef<HTMLInputElement | null>(null)
  const [pendingFile, setPendingFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const onFileSelected = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (!file) return
      if (!file.type.startsWith("image/")) {
        setError("Please choose an image file.")
        return
      }
      if (previewUrl) URL.revokeObjectURL(previewUrl)
      setPendingFile(file)
      setPreviewUrl(URL.createObjectURL(file))
      setError(null)
    },
    [previewUrl],
  )

  const openCamera = useCallback(() => {
    setError(null)
    cameraInputRef.current?.click()
  }, [])

  const openGallery = useCallback(() => {
    setError(null)
    galleryInputRef.current?.click()
  }, [])

  const reset = useCallback(() => {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setPendingFile(null)
    setPreviewUrl(null)
    setError(null)
    if (cameraInputRef.current) cameraInputRef.current.value = ""
    if (galleryInputRef.current) galleryInputRef.current.value = ""
  }, [previewUrl])

  return {
    pendingFile,
    previewUrl,
    error,
    cameraInputRef,
    galleryInputRef,
    onFileSelected,
    openCamera,
    openGallery,
    reset,
  }
}
