import { useCallback } from "react";
import { useDispatch, useSelector } from "react-redux";
import {
  pl2MaxSelector,
  pl2ModeSelector,
  pl2OffsetSelector,
  pl2SupportedSelector,
  setPl2Mode,
  setPl2Offset,
} from "../redux-modules/settingsSlice";
import { Pl2Modes } from "../backend/utils";

export const usePl2Mode = () => {
  const pl2Mode = useSelector(pl2ModeSelector);
  const dispatch = useDispatch();

  const setMode = useCallback((mode: Pl2Modes) => {
    return dispatch(setPl2Mode(mode));
  }, []);

  return { pl2Mode, setPl2Mode: setMode };
};

export const usePl2Offset = () => {
  const pl2Offset = useSelector(pl2OffsetSelector);
  const dispatch = useDispatch();

  const setOffset = useCallback((offset: number) => {
    return dispatch(setPl2Offset(offset));
  }, []);

  return { pl2Offset, setPl2Offset: setOffset };
};

export const usePl2Max = () => useSelector(pl2MaxSelector);

export const usePl2Supported = () => useSelector(pl2SupportedSelector);
