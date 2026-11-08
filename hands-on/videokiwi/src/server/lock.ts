import { mkdir, open, readFile, unlink } from 'node:fs/promises'
import { join } from 'node:path'

export async function lockDataDirectory(directory: string): Promise<() => Promise<void>> {
  await mkdir(directory, { recursive: true })
  const path = join(directory, 'server.lock')
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const handle = await open(path, 'wx', 0o600)
      await handle.writeFile(String(process.pid))
      await handle.close()
      return async () => {
        try { if ((await readFile(path, 'utf8')) === String(process.pid)) await unlink(path) }
        catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error }
      }
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'EEXIST') throw error
      const owner = Number(await readFile(path, 'utf8'))
      if (!Number.isInteger(owner) || owner < 1) throw new Error('데이터 폴더의 server.lock 파일을 확인해 주세요.')
      try { process.kill(owner, 0) }
      catch (probe) {
        if ((probe as NodeJS.ErrnoException).code === 'ESRCH') { await unlink(path); continue }
        throw probe
      }
      throw new Error('이 데이터 폴더를 사용하는 VideoKiwi 서버가 이미 실행 중입니다.')
    }
  }
  throw new Error('데이터 폴더 잠금을 확보하지 못했습니다.')
}
