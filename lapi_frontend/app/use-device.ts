"use client";
import {useEffect,useState} from 'react';
import {currentDevice,type Device} from './screens-client';

/** Phone or computer for this window, updated when it is resized or a foldable opens or closes. */
export function useDevice():Device{
 const [device,setDevice]=useState<Device>(currentDevice());
 useEffect(()=>{
  if(typeof window==='undefined'||typeof window.addEventListener!=='function')return;
  const resized=()=>setDevice(currentDevice());resized();window.addEventListener('resize',resized);return()=>window.removeEventListener('resize',resized);
 },[]);
 return device;
}
